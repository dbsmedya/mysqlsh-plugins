# Copyright (c) 2025, DBS ProxySQL Admin Plugin Contributors
#
# Licensed under the GPL License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""ProxySQL User Administration Module.

This module provides the UserAdmin class for managing synchronization
between MySQL and ProxySQL user accounts.
"""

from typing import Optional, Dict, Any, List
import mysqlsh

from dbs_proxysql_admin.load_proxysql_config import (
    load_proxysql_config,
    load_proxysql_config_from
)


class UserAdmin:
    """Manage synchronization between MySQL and ProxySQL users.

    This class provides methods to synchronize user accounts and passwords
    from MySQL to ProxySQL, including full sync, password updates, and
    orphan cleanup.

    Usage:
        admin = UserAdmin("/path/to/config.ini")
        admin.user_sync()
        admin.update_passwords()
        admin.delete_orphans()
    """

    __all__ = ['user_sync', 'update_passwords', 'delete_orphans', 'reload_config']

    def __init__(self, config_path: Optional[str] = None) -> None:
        """Initialize the UserAdmin instance.

        Args:
            config_path: Optional path to a ProxySQL configuration file.
                If not provided, searches in default locations.

        Raises:
            FileNotFoundError: If no configuration file is found.
            ValueError: If the configuration file is invalid.
        """
        self._shell = mysqlsh.globals.shell
        self._config_path = config_path
        self._cfg: Dict[str, Any] = self._load_config(config_path)
        self._proxysql_default_hostgroup: int = self._cfg.get("default_hostgroup", 0)

        # Get excluded users list from config or use defaults
        default_excluded = ['root', 'admin', 'mysql.sys', 'mysql.session', 'mysql.infoschema']
        self._excluded_users: List[str] = self._cfg.get("excluded_users", default_excluded)

    def _load_config(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """Load configuration from file.

        Args:
            config_path: Optional path to configuration file.

        Returns:
            Dictionary containing configuration values.
        """
        if config_path:
            cfg = load_proxysql_config_from(config_path)
        else:
            cfg = load_proxysql_config()
        return cfg

    @property
    def config_source(self) -> str:
        """Path of the configuration file currently in use."""
        return self._cfg.get("_source", "unknown")

    def target(self) -> Dict[str, Any]:
        """Summarize the ProxySQL target described by the loaded config.

        Returns:
            Dictionary with config_source, host, port, user, default_hostgroup
            and excluded_users.
        """
        return {
            "config_source": self._cfg.get("_source", "unknown"),
            "host": self._cfg.get("host"),
            "port": self._cfg.get("port"),
            "user": self._cfg.get("user"),
            "default_hostgroup": self._proxysql_default_hostgroup,
            "excluded_users": self._excluded_users,
        }

    def _get_shell(self) -> Any:
        """Get the MySQL Shell global object.

        Returns:
            The MySQL Shell global object.
        """
        return mysqlsh.globals.shell

    def _get_session(self) -> Any:
        """Get the current active MySQL session.

        Returns:
            The active MySQL session object.

        Raises:
            ValueError: If no active MySQL session exists.
        """
        session = mysqlsh.globals.session
        if not session or not session.is_open():
            raise ValueError(
                "No active MySQL session. Please connect to a MySQL server first:\n"
                "  \\connect user@host:port"
            )
        return session

    def _open_proxysql_session(self) -> Any:
        """Open a session to ProxySQL admin interface.

        Returns:
            Session object connected to ProxySQL admin.

        Raises:
            Exception: If connection to ProxySQL fails.
        """
        try:
            return self._get_shell().open_session({
                "host": self._cfg["host"],
                "port": self._cfg["port"],
                "user": self._cfg["user"],
                "password": self._cfg["password"],
            })
        except Exception as e:
            raise Exception(
                f"Failed to connect to ProxySQL at {self._cfg['host']}:{self._cfg['port']}: {str(e)}"
            ) from e

    def _fetch_proxysql_users(self, px_session: Any) -> Dict[str, str]:
        """Fetch users from ProxySQL mysql_users table.

        Args:
            px_session: ProxySQL session object.

        Returns:
            Dictionary mapping username to hex-encoded password.
        """
        res = px_session.run_sql("SELECT username, hex(password) FROM mysql_users")
        return {row[0]: row[1] for row in res.fetch_all()}

    def _apply_proxysql_changes(self, px_session: Any) -> None:
        """Apply changes to ProxySQL runtime and persist to disk.

        Args:
            px_session: ProxySQL session object.
        """
        px_session.run_sql("LOAD MYSQL USERS TO RUNTIME")
        px_session.run_sql("SAVE MYSQL USERS TO DISK")

    def _fetch_mysql_users(self) -> Dict[str, str]:
        """Fetch users and their hashed passwords from MySQL server.

        Excludes system users based on the excluded_users configuration.

        Returns:
            Dictionary mapping username to hex-encoded authentication_string.
        """
        session = self._get_session()

        # Static query (no bound parameters): MySQL Shell's run_sql placeholder
        # binder miscounts when a query mixes "?" placeholders with quoted
        # string literals, so the excluded-user filtering is done in Python.
        # Keeping the SQL constant also removes any injection surface.
        query = (
            "SELECT DISTINCT User AS username, hex(authentication_string) "
            "FROM mysql.user WHERE LENGTH(authentication_string) > 0"
        )
        res = session.run_sql(query)

        excluded = set(self._excluded_users or [])
        return {
            row[0]: row[1]
            for row in res.fetch_all()
            if row[0] not in excluded
        }

    def _push_to_proxysql(self, mysql_users: Dict[str, str]) -> Dict[str, Any]:
        """Push MySQL users to ProxySQL.

        Inserts new users and updates passwords for existing users.

        Args:
            mysql_users: Dictionary of username to hex-encoded password.

        Returns:
            Dictionary with operation statistics.
        """
        px = self._open_proxysql_session()
        try:
            existing = self._fetch_proxysql_users(px)
            default_hg = self._proxysql_default_hostgroup

            inserted = 0
            updated = 0

            for username, authstr in mysql_users.items():
                if username not in existing:
                    px.run_sql(
                        "INSERT INTO mysql_users(username, password, default_hostgroup) "
                        "VALUES (?, unhex(?), ?)",
                        [username, authstr, default_hg],
                    )
                    inserted += 1
                elif existing[username] != authstr:
                    px.run_sql(
                        "UPDATE mysql_users SET password = unhex(?) WHERE username = ?",
                        [authstr, username],
                    )
                    updated += 1

            if inserted > 0 or updated > 0:
                self._apply_proxysql_changes(px)

            return {
                "count": inserted + updated,
                "inserted": inserted,
                "updated": updated
            }
        finally:
            px.close()

    def user_sync(self) -> Dict[str, Any]:
        """Perform full synchronization (insert + update, no deletions).

        Adds new users and updates existing passwords from MySQL to ProxySQL.

        Returns:
            Dictionary with operation statistics containing keys:
                - count: Total number of users synchronized
                - inserted: Number of new users inserted
                - updated: Number of existing users updated
        """
        users = self._fetch_mysql_users()
        return self._push_to_proxysql(users)

    def update_passwords(self) -> Dict[str, Any]:
        """Update passwords in ProxySQL for users that exist in both systems.

        Only updates passwords that have changed.

        Returns:
            Dictionary with operation statistics containing keys:
                - count: Number of passwords updated
        """
        mysql_users = self._fetch_mysql_users()
        px = self._open_proxysql_session()
        try:
            existing = self._fetch_proxysql_users(px)

            updated = 0
            for userhost, authstr in mysql_users.items():
                if userhost in existing and existing[userhost] != authstr:
                    px.run_sql(
                        "UPDATE mysql_users SET password = unhex(?) WHERE username = ?",
                        [authstr, userhost],
                    )
                    updated += 1

            if updated > 0:
                self._apply_proxysql_changes(px)

            return {"count": updated}
        finally:
            px.close()

    def delete_orphans(self) -> Dict[str, Any]:
        """Delete users from ProxySQL that don't exist in MySQL.

        Useful for cleanup after users are removed from MySQL.

        Returns:
            Dictionary with operation statistics containing keys:
                - count: Number of orphaned users deleted
        """
        mysql_users = self._fetch_mysql_users()
        px = self._open_proxysql_session()
        try:
            existing = self._fetch_proxysql_users(px)

            extra = set(existing) - set(mysql_users)
            for username in extra:
                px.run_sql("DELETE FROM mysql_users WHERE username = ?", [username])

            if extra:
                self._apply_proxysql_changes(px)

            return {"count": len(extra)}
        finally:
            px.close()

    def reload_config(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """Reload configuration and verify ProxySQL connectivity.

        Args:
            config_path: Optional path to config file. If None, uses current config.

        Returns:
            Dictionary with reload result containing keys:
                - source: Path of the loaded configuration file

        Raises:
            Exception: If configuration reload or connection fails.
        """
        if config_path:
            self._cfg = self._load_config(config_path)
            self._config_path = config_path
        else:
            self._cfg = self._load_config(self._config_path)

        # Verify connectivity
        px = self._open_proxysql_session()
        try:
            # Test query
            px.run_sql("SELECT 1")
        finally:
            px.close()

        return {"source": self._cfg.get("_source", "unknown")}
