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

"""Plugin registration

This file is automatically loaded by the MySQL Shell at startup time.

It registers the plugin objects and then imports all sub-modules to
register the plugin object member functions.

Two plugin objects are registered:
  - dbs.proxysql.admin - the current command based API, grouped under the
    shared "dbs" brand namespace (so future DBS plugins can live under
    dbs.* too).
  - dbs_proxysql_admin - a legacy compatibility object exposing create().
"""

from typing import Optional
from mysqlsh.plugin_manager import plugin, plugin_function
from dbs_proxysql_admin.user_admin import UserAdmin
from dbs_proxysql_admin import admin_core
from dbs_proxysql_admin.load_proxysql_config import (
    load_proxysql_config,
    load_proxysql_config_from,
    find_existing_config,
)


@plugin
class dbs:
    """DBS MySQL Shell tools.

    Brand namespace for DBS MySQL Shell plugins. Individual toolsets are
    grouped under it, for example dbs.proxysql for ProxySQL administration.
    """

    class proxysql:
        """DBS ProxySQL user sync tools.

        Utilities to synchronize MySQL users with ProxySQL - full user sync
        (insert and update, no deletes), password updates, orphan cleanup and
        configuration management.
        """

        class admin:
            """ProxySQL user administration functions."""


@plugin_function("dbs.proxysql.admin.userSync", cli=True, shell=True)
def user_sync(config_path: Optional[str] = None) -> dict:
    """Perform a full user sync from MySQL to ProxySQL.

    This function inserts new users and updates existing passwords from MySQL
    to ProxySQL. It does NOT delete users from ProxySQL.

    Args:
        config_path (str): Path to a ProxySQL configuration file. If not
            provided, the active config is used, then the default search.

    Returns:
        dict: The operation result with success, message, users_synced and
        config_source keys.

    Examples:
        >>> dbs.proxysql.admin.userSync()
        >>> dbs.proxysql.admin.userSync("/path/to/config.ini")
    """
    interactive = admin_core.get_interactive_default()
    try:
        path = admin_core.ensure_config(config_path, interactive)
        admin = UserAdmin(config_path=path)
        result = admin.user_sync()
        return {
            "success": True,
            "message": "Users synchronized successfully",
            "users_synced": result.get("count", 0),
            "config_source": admin.config_source
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to sync users: {str(e)}",
            "users_synced": 0
        }


@plugin_function("dbs.proxysql.admin.updatePasswords", cli=True, shell=True)
def update_passwords(config_path: Optional[str] = None) -> dict:
    """Update passwords in ProxySQL for existing users.

    This function updates passwords in ProxySQL for users that exist in both
    MySQL and ProxySQL. Only passwords that have changed are updated.

    Args:
        config_path (str): Path to a ProxySQL configuration file. If not
            provided, the active config is used, then the default search.

    Returns:
        dict: The operation result with success, message, passwords_updated and
        config_source keys.

    Examples:
        >>> dbs.proxysql.admin.updatePasswords()
        >>> dbs.proxysql.admin.updatePasswords("/path/to/config.ini")
    """
    interactive = admin_core.get_interactive_default()
    try:
        path = admin_core.ensure_config(config_path, interactive)
        admin = UserAdmin(config_path=path)
        result = admin.update_passwords()
        return {
            "success": True,
            "message": "Passwords updated successfully",
            "passwords_updated": result.get("count", 0),
            "config_source": admin.config_source
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to update passwords: {str(e)}",
            "passwords_updated": 0
        }


@plugin_function("dbs.proxysql.admin.deleteOrphans", cli=True, shell=True)
def delete_orphans(config_path: Optional[str] = None) -> dict:
    """Delete users from ProxySQL that don't exist in MySQL.

    This function is useful for cleanup after users are removed from MySQL.
    It identifies users in ProxySQL that no longer exist in MySQL and removes them.

    Args:
        config_path (str): Path to a ProxySQL configuration file. If not
            provided, the active config is used, then the default search.

    Returns:
        dict: The operation result with success, message, users_deleted and
        config_source keys.

    Examples:
        >>> dbs.proxysql.admin.deleteOrphans()
        >>> dbs.proxysql.admin.deleteOrphans("/path/to/config.ini")
    """
    interactive = admin_core.get_interactive_default()
    try:
        path = admin_core.ensure_config(config_path, interactive)
        admin = UserAdmin(config_path=path)
        result = admin.delete_orphans()
        return {
            "success": True,
            "message": "Orphaned users deleted successfully",
            "users_deleted": result.get("count", 0),
            "config_source": admin.config_source
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to delete orphans: {str(e)}",
            "users_deleted": 0
        }


@plugin_function("dbs.proxysql.admin.reloadConfig", cli=True, shell=True)
def reload_config(config_path: Optional[str] = None) -> dict:
    """Reload the ProxySQL configuration and verify connectivity.

    This function reloads the configuration file and attempts to connect
    to ProxySQL to verify the configuration is valid.

    Args:
        config_path (str): Path to a ProxySQL configuration file. If not
            provided, the active config is used, then the default search.

    Returns:
        dict: The operation result with success, message and config_source keys.

    Examples:
        >>> dbs.proxysql.admin.reloadConfig()
        >>> dbs.proxysql.admin.reloadConfig("/path/to/config.ini")
    """
    interactive = admin_core.get_interactive_default()
    try:
        path = admin_core.ensure_config(config_path, interactive)
        admin = UserAdmin(config_path=path)
        result = admin.reload_config()
        return {
            "success": True,
            "message": "Configuration reloaded successfully",
            "config_source": result.get("source", admin.config_source)
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to reload config: {str(e)}",
            "config_source": config_path or "default"
        }


@plugin_function("dbs.proxysql.admin.getConfigPath", cli=True, shell=True)
def get_config_path() -> dict:
    """Get the default configuration file search paths.

    Returns:
        dict: The search configuration with paths and environment_var keys.

    Examples:
        >>> dbs.proxysql.admin.getConfigPath()
    """
    from dbs_proxysql_admin.load_proxysql_config import DEFAULT_PATHS

    return {
        "paths": [str(p) for p in DEFAULT_PATHS],
        "environment_var": "PROXYSQL_SYNC_CONFIG"
    }


@plugin_function("dbs.proxysql.admin.useConfig", cli=True, shell=True)
def use_config(config_path: Optional[str] = None) -> dict:
    """Set the active ProxySQL configuration for this shell session.

    Commands called afterwards without an explicit config_path will use this
    configuration. The setting is session scoped and resets when the MySQL
    Shell is restarted. Use this to pick which ProxySQL server to act on when
    several configuration files exist.

    Args:
        config_path (str): Path to the ProxySQL configuration file to activate.

    Returns:
        dict: The result with success, message, config_source and proxysql keys.

    Examples:
        >>> dbs.proxysql.admin.useConfig("/etc/proxysql/service_accounts.ini")
    """
    interactive = admin_core.get_interactive_default()
    try:
        if not config_path and interactive:
            config_path = admin_core.prompt("Path to ProxySQL config: ").strip()
        if not config_path:
            raise ValueError("The config_path parameter is required.")

        cfg = load_proxysql_config_from(config_path)
        admin_core.set_active_config_path(config_path)
        return {
            "success": True,
            "message": "Active ProxySQL config set",
            "config_source": cfg.get("_source"),
            "proxysql": f"{cfg.get('host')}:{cfg.get('port')}"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to set active config: {str(e)}"
        }


@plugin_function("dbs.proxysql.admin.clearConfig", cli=True, shell=True)
def clear_config() -> dict:
    """Clear the active ProxySQL configuration for this session.

    After clearing, commands fall back to the default configuration search
    locations unless an explicit config_path is provided.

    Returns:
        dict: The result with success and message keys.

    Examples:
        >>> dbs.proxysql.admin.clearConfig()
    """
    admin_core.clear_active_config_path()
    return {
        "success": True,
        "message": "Active config cleared; default search will be used."
    }


@plugin_function("dbs.proxysql.admin.status", cli=True, shell=True)
def status() -> dict:
    """Show which ProxySQL configuration is currently in effect.

    Reports the active configuration (if set), the configuration file that
    would actually be used, the resolved ProxySQL admin host and port, the
    user exclusion filter and whether a MySQL session is connected.

    Returns:
        dict: A summary of the active and effective configuration.

    Examples:
        >>> dbs.proxysql.admin.status()
    """
    active = admin_core.get_active_config_path()
    info = {
        "active_config": active,
        "mysql_session_connected": admin_core.mysql_session_connected()
    }
    try:
        if active:
            cfg = load_proxysql_config_from(active)
            info["config_in_use"] = "active"
        elif find_existing_config() is not None:
            cfg = load_proxysql_config()
            info["config_in_use"] = "default-search"
        else:
            info["config_in_use"] = "none"
            info["message"] = (
                "No ProxySQL config found. Run createConfig() to create one."
            )
            return info

        info["config_source"] = cfg.get("_source")
        info["proxysql"] = f"{cfg.get('host')}:{cfg.get('port')}"
        info["proxysql_user"] = cfg.get("user")
        info["default_hostgroup"] = cfg.get("default_hostgroup")
        info["excluded_users"] = cfg.get("excluded_users")
        info["required_host"] = cfg.get("required_host")
    except Exception as e:
        info["config_in_use"] = "error"
        info["message"] = str(e)
    return info


@plugin_function("dbs.proxysql.admin.createConfig", cli=True, shell=True)
def create_config(config_path: Optional[str] = None, host: Optional[str] = None,
                  port: Optional[int] = None, user: Optional[str] = None,
                  password: Optional[str] = None,
                  default_hostgroup: Optional[int] = None,
                  excluded_users: Optional[str] = None,
                  required_host: Optional[str] = None) -> dict:
    """Create a ProxySQL configuration file, interactively when possible.

    In the interactive shell this runs a wizard that asks for the ProxySQL
    admin host, port, user, password, default hostgroup and the excluded user
    list, then writes the configuration file. Provide any argument to skip the
    matching question. Use this to create the first default configuration or
    additional profiles for other ProxySQL servers.

    Args:
        config_path (str): Where to write the file. Defaults to the user home
            configuration file when omitted.
        host (str): ProxySQL admin host.
        port (int): ProxySQL admin port.
        user (str): ProxySQL admin user.
        password (str): ProxySQL admin password.
        default_hostgroup (int): Default hostgroup for newly added users.
        excluded_users (str): Comma separated list of users to exclude.
        required_host (str): mysql.user Host of the accounts to sync, for
            example % or 10.%. Defaults to %. Changing it later can rewrite
            already-synced ProxySQL passwords with the new host's values.

    Returns:
        dict: The result with success, message, config_source and proxysql keys.

    Examples:
        >>> dbs.proxysql.admin.createConfig()
        >>> dbs.proxysql.admin.createConfig("/etc/proxysql/service.ini")
    """
    interactive = admin_core.get_interactive_default()
    try:
        provided = {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "default_hostgroup": default_hostgroup,
            "excluded_users": excluded_users,
            "required_host": required_host
        }
        provided = {k: v for k, v in provided.items() if v is not None}

        path, values = admin_core.run_config_wizard(
            config_path, provided, interactive)
        return {
            "success": True,
            "message": "ProxySQL configuration created",
            "config_source": path,
            "proxysql": f"{values['host']}:{values['port']}",
            "hint": f"Run useConfig('{path}') to activate it."
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to create config: {str(e)}"
        }


# ---------------------------------------------------------------------------
# Legacy compatibility API (v0.9.x)
#
# Kept so existing scripts that call dbs_proxysql_admin.create() keep working.
# New code should prefer the dbs.proxysql.admin.* commands above.
# ---------------------------------------------------------------------------


@plugin
class dbs_proxysql_admin:
    """Legacy DBS ProxySQL user sync tools (compatibility object).

    Deprecated. This object is kept only so existing scripts that call
    dbs_proxysql_admin.create() continue to work. New code should use the
    dbs.proxysql.admin commands instead.
    """


@plugin_function("dbs_proxysql_admin.create")
def create(config_path: Optional[str] = None):
    """Create a ProxySQL user management toolset (legacy API).

    Deprecated. Prefer dbs.proxysql.admin.userSync() and the related commands.
    Returns an object whose methods operate on the configuration loaded at
    create() time.

    Args:
        config_path (str): Optional path to a ProxySQL configuration file.

    Returns:
        dict: A toolset of callables that mysqlsh exposes as an extension
        object, with userSync, updatePasswords, deleteOrphans and reloadConfig.
    """
    admin = UserAdmin(config_path=config_path)

    # Return a dict of callables; mysqlsh turns this into an extension object.
    return {
        "userSync": lambda: admin.user_sync(),
        "updatePasswords": lambda: admin.update_passwords(),
        "deleteOrphans": lambda: admin.delete_orphans(),
        "reloadConfig": lambda: admin.reload_config(),
    }
