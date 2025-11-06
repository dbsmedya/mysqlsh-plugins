from typing import Optional
from mysqlsh.plugin_manager import plugin, plugin_function
from dbs_proxysql_admin.user_admin import user_admin


@plugin
class dbs_proxysql_admin:
    """
    DBS ProxySQL user sync tools.

    This plugin provides utilities to synchronize MySQL users with ProxySQL.

    It can:
      - Perform a full user sync from MySQL to ProxySQL (insert and update, no deletes)
      - Update ProxySQL passwords for existing users
      - Delete ProxySQL users that no longer exist in MySQL
      - Reload the ProxySQL admin configuration
    """


@plugin_function("dbs_proxysql_admin.create")
def create(config_path: Optional[str] = None):
    """
    Create a ProxySQL user management toolset.

    Args:
      config_path (string): Optional path to a ProxySQL configuration file.

    Returns:
        A dict of callables; mysqlsh turns this into an extension object.
    """
    admin = user_admin(config_path=config_path)

    # Return a dict of callables; mysqlsh turns this into an extension object.
    return {
        "userSync": lambda: admin.user_sync(),
        "updatePasswords": lambda: admin.update_passwords(),
        "deleteOrphans": lambda: admin.delete_orphans(),
        "reloadConfig": lambda: admin.reload_config(),
    }

@plugin_function("dbs_proxysql_admin.userSync")
def user_sync():
    pass