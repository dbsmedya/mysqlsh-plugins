import mysqlsh
from typing import Optional, Dict, Any
from dbs_proxysql_admin.load_proxysql_config import (
    load_proxysql_config, load_proxysql_config_from
)

class user_admin():
    """
    Manage synchronization between MySQL and ProxySQL.
    Usage:
        proxysql = dbs_proxysql_admin("/path/to/config.ini")
        proxysql.user_sync()
    """

    __all__ = ['user_sync', 'update_passwords', 'delete_orphans', 'reload_config']

    def __init__(self, config_path: Optional[str] = None) -> None:
        self.shell: Any = mysqlsh.globals.shell
        self.session: Any = mysqlsh.globals.session

        if config_path:
            self.cfg: Dict[str, Any] = load_proxysql_config_from(config_path)
        else:
            self.cfg: Dict[str, Any] = load_proxysql_config()

        self.proxysql_default_hostgroup: int = self.cfg.get("default_hostgroup", 0)
        
        # Get excluded users list from config or use defaults
        default_excluded = ['root', 'admin']
        self.excluded_users: list = self.cfg.get("excluded_users", default_excluded)

        print(f"[proxysqlAdmin] Config loaded from {self.cfg['_source']}")


    # --- Private helpers ---
    def __open_px_session(self):
        """
        Open a session to ProxySQL admin interface.
        
        Returns:
            Session object connected to ProxySQL
            
        Raises:
            Exception: If connection to ProxySQL fails
        """
        try:
            return self.shell.open_session({
                "host": self.cfg["host"],
                "port": self.cfg["port"],
                "user": self.cfg["user"],
                "password": self.cfg["password"],
            }, self.cfg["password"])
        except Exception as e:
            raise Exception(f"Failed to connect to ProxySQL: {str(e)}") from e

    def __get_mysql_session(self):
        """
        Get the current MySQL session.
        
        Returns:
            Active MySQL session object
            
        Raises:
            ValueError: If no active MySQL session exists
        """
        if not self.session or not self.session.is_open():
            raise ValueError("No active MySQL session. Connect first in mysqlsh.")
        return self.session

    def __fetch_proxysql_users(self, px ) -> Dict[str, str]:
        """
        Internal function to fetch users from ProxySQL mysql_users table.
        
        Args:
            px: ProxySQL session object
            
        Returns:
            dict: Mapping of username to hex-encoded password
        """
        res = px.run_sql("SELECT username, hex(password) FROM mysql_users")
        return {r[0]: r[1] for r in res.fetch_all()}

    def __apply_proxysql_changes(self, px) -> None:
        """
        Internal function to apply changes to ProxySQL runtime and persist to disk.
        
        Args:
            px: ProxySQL session object
        """
        px.run_sql("LOAD MYSQL USERS TO RUNTIME")
        px.run_sql("SAVE MYSQL USERS TO DISK")

    def __pull_mysql_users(self) -> Dict[str, str]:
        """
        Fetch users and their hashed passwords from MySQL server.
        Excludes system users based on excluded_users configuration.
        
        Returns:
            dict: Mapping of username to hex-encoded authentication_string
        """
        sess = self.__get_mysql_session()
        
        # Build placeholders for parameterized query
        placeholders = ','.join(['?' for _ in self.excluded_users])
        query = f"SELECT DISTINCT User AS userhost, hex(authentication_string) FROM mysql.user WHERE User NOT IN ({placeholders})"
        
        res = sess.run_sql(query, self.excluded_users)
        return {r[0]: r[1] for r in res.fetch_all()}

    def __push_to_proxysql(self, mysql_users: Dict[str, str]) -> None:
        """
        Push MySQL users to ProxySQL, inserting new users and updating passwords.
        
        Args:
            mysql_users (dict): Dictionary of username to hex-encoded password
        """
        px = self.__open_px_session()
        try:
            existing = self.__fetch_proxysql_users(px)
            default_hg = self.proxysql_default_hostgroup

            for username, authstr in mysql_users.items():
                if username not in existing:
                    px.run_sql(
                        "INSERT INTO mysql_users(username,password,default_hostgroup) VALUES (?,unhex(?),?)",
                        [username, authstr, default_hg],
                    )
                elif existing[username] != authstr:
                    px.run_sql(
                        "UPDATE mysql_users SET password=unhex(?) WHERE username=?",
                        [authstr, username],
                    )

            self.__apply_proxysql_changes(px)
            print("ProxySQL users inserted/updated.")
        finally:
            px.close()

    # --- Core methods ---
    def update_passwords(self) -> None:
        """
        Update passwords in ProxySQL for users that exist in both MySQL and ProxySQL.
        Only updates passwords that have changed.
        """
        mysql_users = self.__pull_mysql_users()
        px = self.__open_px_session()
        try:
            existing = self.__fetch_proxysql_users(px)

            for userhost, authstr in mysql_users.items():
                if userhost in existing and existing[userhost] != authstr:
                    px.run_sql(
                        "UPDATE mysql_users SET password=unhex(?) WHERE username=?",
                        [authstr, userhost],
                    )

            self.__apply_proxysql_changes(px)
            print("ProxySQL user passwords updated.")
        finally:
            px.close()

    def delete_orphans(self) -> None:
        """
        Delete users from ProxySQL that don't exist in MySQL.
        Useful for cleanup after users are removed from MySQL.
        """
        mysql_users = self.__pull_mysql_users()
        px = self.__open_px_session()
        try:
            existing = self.__fetch_proxysql_users(px)

            extra = set(existing) - set(mysql_users)
            for username in extra:
                px.run_sql("DELETE FROM mysql_users WHERE username=?", [username])

            if extra:
                self.__apply_proxysql_changes(px)
            print(f"Deleted {len(extra)} orphaned ProxySQL users.")
        finally:
            px.close()

    def user_sync(self) -> None:
        """
        Full synchronization (insert + update, no deletions).
        Adds new users and updates existing passwords from MySQL to ProxySQL.
        """
        users = self.__pull_mysql_users()
        self.__push_to_proxysql(users)

    def reload_config(self, config_path: Optional[str] = None) -> None:
        """
        Reload config file dynamically.
        
        Args:
            config_path (str, optional): Path to config file. If None, uses default location.
        """
        if config_path:
            self.cfg = load_proxysql_config_from(config_path)
        else:
            self.cfg = load_proxysql_config()
