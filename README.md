# MySQL Shell ProxySQL Admin Plugin

A MySQL Shell plugin for synchronizing MySQL users with ProxySQL. This plugin provides utilities to manage user synchronization between your MySQL server and ProxySQL user management layer.

This tool is inspired by https://github.com/lefred/mysqlshell-plugins/tree/master/proxysql. Lefred's implementation refers to a historic ProxySQL version and does not support [caching_sha2_passwords](https://dev.mysql.com/doc/refman/8.4/en/caching-sha2-pluggable-authentication.html) for MySQL LTS 8.4 series. 

Percona PXC also has a quite powerful [ProxySQL admin tool](https://github.com/percona/proxysql-admin-tool) for their PXC build which supports Galera replication. 

ProxySQL version > 2.7 has now built-in support for [MySQL Group Replication (GR) Bootstrap Mode](https://proxysql.com/documentation/proxysql-bootstrap-mode/), so if you use GR, prefer ProxySQL's built-in method.

There are also modules written in Python and other languages which will support those functions, but this tool was developed to achieve no dependency for 3rd party python libraries, mostly restricted on production database environments. It only uses MySQL Shell's built-in mysql session for connecting to the ProxySQL admin interface via MySQL protocol.

This version works with [caching_sha2_passwords](https://proxysql.com/documentation/password-management/)  supported by ProxySQL > 2.6 or later. Upcomming release will support MySQL [Dual-Passwords](https://dev.mysql.com/doc/refman/8.4/en/password-management.html#dual-passwords) as well

## Features

- **Full User Sync**: Synchronize all MySQL users to ProxySQL (insert new users and update existing passwords)
- **Password Updates**: Update ProxySQL passwords for existing users when they change in MySQL
- **Orphan Cleanup**: Delete ProxySQL users that no longer exist in MySQL
- **Configuration Management**: Flexible configuration file support with environment variable overrides
- **User Filtering**: Exclude system users and other unwanted accounts from synchronization

## Prerequisites

- MySQL Shell 8.4 or later
- Access to both MySQL server and ProxySQL admin interface

## Installation

### Method 1: Clone Repository

```bash
# Clone the repository to your MySQL Shell plugins directory
git clone https://github.com/dbsmedya/mysqlsh-plugins.git ~/.mysqlsh/plugins/

# Or clone to a custom location and set MYSQLSH_USER_CONFIG_HOME
git clone https://github.com/dbsmedya/mysqlsh-plugins.git /path/to/plugins/
export MYSQLSH_USER_CONFIG_HOME=/path/to/plugins/
```

### Method 2: Manual Installation

1. Download the plugin files
2. Create the plugin directory structure:
   ```bash
   mkdir -p ~/.mysqlsh/plugins/dbs_proxysql_admin/
   ```
3. Copy all files from `dbs_proxysql_admin/` to the created directory

### Verify Installation

Start MySQL Shell and verify the plugin is loaded:

```bash
mysqlsh
```

In MySQL Shell:
```javascript
// Check if plugin is available
MySQL Shell > \py
MySQL Shell > help(dbs_proxysql_admin)
```

## Configuration

### Configuration File Setup

The plugin looks for configuration files in the following order:

1. Path specified by `PROXYSQL_SYNC_CONFIG` environment variable
2. `~/.proxysql_config.ini`
3. `/etc/proxysql_sync.conf`
4. `~/.mysqlsh/plugins/dbs_proxysql_admin/proxysql_config.ini` (Example file)

Create a configuration file (e.g., `~/.proxysql_config.ini`):

```ini
[proxysql]
# ProxySQL Admin Interface Connection
host = 127.0.0.1
port = 6032
user = admin
password = admin

# Default hostgroup for new users
default_hostgroup = 0

# Comma-separated list of MySQL users to exclude from synchronization
excluded_users = mysql.sys,mysql.session,mysql.infoschema,root,admin
```

### Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `host` | ProxySQL admin interface host | `127.0.0.1` |
| `port` | ProxySQL admin interface port | `6032` |
| `user` | ProxySQL admin username | `admin` |
| `password` | ProxySQL admin password | `admin` |
| `default_hostgroup` | Default hostgroup ID for new users | `0` |
| `excluded_users` | Comma-separated list of users to exclude | `mysql.sys,mysql.session,mysql.infoschema,root,admin` |

### Environment Variables

You can specify a custom config file location:

```bash
export PROXYSQL_SYNC_CONFIG="/path/to/your/config.ini"
```

## Usage

### Basic Usage

1. **Connect to MySQL** in MySQL Shell:
   ```javascript
   \connect user@mysql-host:3306
   ```

2. **Create the plugin instance**:
   ```python
   \py
   # Using default config file location
   proxysql = mysqlsh.plugins.dbs_proxysql_admin.create()
   
   # Or specify a custom config file
   proxysql = mysqlsh.plugins.dbs_proxysql_admin.create("/path/to/config.ini")
   ```

### Available Operations

#### Full User Synchronization
Synchronizes all MySQL users to ProxySQL (adds new users and updates existing passwords):

```python
proxysql.userSync()
```

#### Update Passwords Only
Updates passwords in ProxySQL for existing users:

```python
proxysql.updatePasswords()
```

#### Delete Orphaned Users
Removes ProxySQL users that no longer exist in MySQL:

```python
proxysql.deleteOrphans()
```

#### Reload Configuration
Reloads the configuration file (useful for dynamic config changes):

```python
proxysql.reloadConfig()
# Or reload from a different config file
proxysql.admin.reloadConfig("/path/to/new/config.ini")
```

### Example Workflow

```python
 MySQL 127.0.0.1:3306 ssl SQL >\py
# Connect to MySQL first
\connect root@localhost:3306

# Create admin instance
proxysql = mysqlsh.plugins.dbs_proxysql_admin.create()

# Perform initial full sync
proxysql.userSync()

# Later, if passwords change, update them
proxysql.updatePasswords()

# Clean up users that were removed from MySQL
proxysql.deleteOrphans()
```

### JavaScript Usage

```javascript
// Connect to MySQL
\connect user@mysql-host:3306

proxysql = mysqlsh.plugins.dbs_proxysql_admin.create()
proxysql.userSync()

```

## Security Considerations

1. **Secure Configuration Files**: Store configuration files with restrictive permissions:
   ```bash
   chmod 600 ~/.proxysql_config.ini
   ```

2. **Network Security**: Ensure ProxySQL admin interface is not exposed to untrusted networks

3. **User Filtering**: Review and customize the `excluded_users` list to prevent synchronization of sensitive accounts

4. **Password Management**: Consider using environment variables or secure secret management for passwords

## Troubleshooting

### Common Issues

1. **Plugin Not Found**
   ```
   Error: Module 'dbs_proxysql_admin' not found
   ```
   - Verify plugin installation path
   - Check `MYSQLSH_USER_CONFIG_HOME` environment variable
   - Restart MySQL Shell after installation

2. **Configuration File Not Found**
   ```
   FileNotFoundError: No ProxySQL config found
   ```
   - Create configuration file in one of the expected locations
   - Set `PROXYSQL_SYNC_CONFIG` environment variable
   - Verify file permissions and format

3. **ProxySQL Connection Failed**
   ```
   Failed to connect to ProxySQL: Connection refused
   ```
   - Verify ProxySQL admin interface is running
   - Check host, port, username, and password in config
   - Ensure network connectivity to ProxySQL

4. **MySQL Session Required**
   ```
   ValueError: No active MySQL session
   ```
   - Connect to MySQL server first using `\connect`
   - Ensure the MySQL connection is active

5. **User 'admin' can only connect locally**
   ````
   Failed to connect to ProxySQL: MySQL Error (1040): Shell.open_session: User 'admin' can only connect locally
   ````
   - Proxysql only allows 'admin' username to be connect from localhost. Create another remote admin user and password for Proxysql in username:password format.

   ```sql
   MySQL [(none)]> set admin-admin_credentials='admin:admin;radmin:remoteAdminPassword';
   Query OK, 1 row affected (0.001 sec)

   MySQL [(none)]> save admin variables to disk;
   Query OK, 50 rows affected (0.007 sec)

   MySQL [(none)]> load admin variables to runtime;
   Query OK, 0 rows affected (0.003 sec)
   ````

   - Update the proxysql_config.ini with new credentials. 
   ```ini
    [proxysql]
    user = radmin
    password = remoteAdminPassword
   ```

### Debug Mode

Enable verbose output by checking the plugin logs:

```python
\py
import logging
logging.basicConfig(level=logging.DEBUG)

# Then run your admin operations
proxysql = dbs_proxysql_admin.create()
proxysql.userSync()
```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes and add tests
4. Commit your changes: `git commit -am 'Add some feature'`
5. Push to the branch: `git push origin feature/your-feature`
6. Submit a pull request

## License

This project is licensed under the terms specified in the LICENSE file.

## Support

For issues and questions:

1. Check the [troubleshooting section](#troubleshooting)
2. Search existing issues in the GitHub repository
3. Create a new issue with detailed information about your problem
4. Professional support and consulting services are available at [dbsmedya.com](https://dbsmedya.com)


## Trademarks

- MySQL® is a registered trademark of Oracle Corporation and/or its affiliates
- MariaDB® is a registered trademark of MariaDB Corporation Ab
- ProxySQL™ is a trademark of ProxySQL LLC

---

**Note**: This plugin requires an active MySQL connection in MySQL Shell and proper ProxySQL configuration. Always test in a development environment before using in production.

---

**Developed by**: [dbsmedya](https://dbsmedya.com) - Professional MySQL and database consulting services