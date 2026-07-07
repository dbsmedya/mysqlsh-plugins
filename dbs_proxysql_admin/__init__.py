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

"""DBS ProxySQL Admin Plugin for MySQL Shell.

This plugin provides utilities to synchronize MySQL users with ProxySQL.

Commands live under dbs.proxysql.admin. The object tokens read the same in
both languages; only the function names follow the active language, so in
Python use snake_case (dbs.proxysql.admin.user_sync()) and in JavaScript
camelCase (dbs.proxysql.admin.userSync()).

Sync commands:
    dbs.proxysql.admin.userSync(config_path)        - Full user sync from MySQL to ProxySQL
    dbs.proxysql.admin.updatePasswords(config_path) - Update passwords for existing users
    dbs.proxysql.admin.deleteOrphans(config_path)   - Delete ProxySQL users not in MySQL
    dbs.proxysql.admin.reloadConfig(config_path)    - Reload configuration and verify connection

Configuration commands:
    dbs.proxysql.admin.status()                     - Show which config is currently in effect
    dbs.proxysql.admin.useConfig(config_path)       - Set the active config for this session
    dbs.proxysql.admin.clearConfig()                - Clear the active config (use default search)
    dbs.proxysql.admin.createConfig(...)            - Create a config file (interactive wizard)
    dbs.proxysql.admin.getConfigPath()              - Show default config file search paths

Legacy (deprecated, kept for backward compatibility):
    proxysql = dbs_proxysql_admin.create(config_path)
    proxysql.userSync()

Working with several ProxySQL servers:
    Keep one .ini per server (e.g. service accounts vs user accounts). Select
    the one to act on with useConfig(); status() shows the active target and
    every sync result reports the config_source it used. The active config is
    session scoped and resets when the shell restarts. On a fresh install,
    running a sync command interactively offers to create the first config.

Configuration:
    A config file is selected in the following order:
    1. An explicit config_path argument
    2. The active config set with useConfig()
    3. Path specified in the PROXYSQL_SYNC_CONFIG environment variable
    4. ~/.proxysql_config.ini
    5. /etc/proxysql_sync.conf
    6. ./proxysql_config.ini

Example configuration file:
    [proxysql]
    host = 127.0.0.1
    port = 6032
    user = radmin
    password = radmin
    default_hostgroup = 0
    excluded_users = root, admin, mysql.sys
    required_host = %

    required_host selects which mysql.user Host row is synchronized (MySQL
    accounts are keyed by User AND Host). Only accounts with that exact Host
    value are synced. Changing it later can rewrite already-synced ProxySQL
    passwords with the new host row's values; see README.md.
"""
