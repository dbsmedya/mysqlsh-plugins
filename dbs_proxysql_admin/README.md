# DBS ProxySQL Admin Plugin for MySQL Shell

A MySQL Shell plugin for managing ProxySQL user synchronization with MySQL.

Commands live under the `dbs.proxysql.admin` object — `dbs` is the DBS brand
namespace, so future DBS plugins can register alongside it (`dbs.proxysql`,
`dbs.performance`, …) without claiming the bare `proxysql` global.

## Background and scope

This plugin is inspired by [lefred's mysqlshell-plugins/proxysql](https://github.com/lefred/mysqlshell-plugins/tree/master/proxysql).
That historic implementation targets an older ProxySQL and does not support
[`caching_sha2_password`](https://dev.mysql.com/doc/refman/8.4/en/caching-sha2-pluggable-authentication.html),
the default authentication plugin of the MySQL 8.4 LTS series. This plugin syncs
`caching_sha2_password` hashes correctly, which requires
[ProxySQL ≥ 2.6](https://proxysql.com/documentation/password-management/).

It has **no third-party Python dependencies** — it talks to the ProxySQL admin
interface over the MySQL protocol using only MySQL Shell's built-in session, so
it installs and runs on locked-down production hosts where extra packages are not
allowed. For Galera/PXC clusters, Percona's
[proxysql-admin-tool](https://github.com/percona/proxysql-admin-tool) is more
capable; and if you run MySQL Group Replication, ProxySQL ≥ 2.7 ships a built-in
[GR bootstrap mode](https://proxysql.com/documentation/proxysql-bootstrap-mode/)
that you should prefer. A future release will add support for MySQL
[dual passwords](https://dev.mysql.com/doc/refman/8.4/en/password-management.html#dual-passwords).

## Features

- **User Synchronization**: Sync MySQL users to ProxySQL (insert new users, update passwords)
- **Password Updates**: Update only changed passwords for existing users
- **Orphan Cleanup**: Remove ProxySQL users that no longer exist in MySQL
- **Multiple ProxySQL targets**: Keep one config file per server and switch between them at runtime
- **Config wizard**: Create configuration files interactively, including a guided first-run setup
- **CLI & Shell Support**: Works in both interactive shell and command-line modes
- **Backward compatible**: The legacy `dbs_proxysql_admin.create()` API still works

## Naming in Python vs JavaScript

The object tokens `dbs.proxysql.admin` are identical in both languages. Only the
**function names** follow the active language convention:

| | Python (`\py`) | JavaScript (`\js`) |
|---|---|---|
| Example | `dbs.proxysql.admin.user_sync()` | `dbs.proxysql.admin.userSync()` |
| CLI | `mysqlsh -- dbs proxysql admin userSync` | (same) |

This README uses the JavaScript/CLI spelling (`userSync`); in Python use the
snake_case form (`user_sync`).

## Installation

1. Clone or copy this directory to your MySQL Shell plugins folder:
   ```bash
   # Option 1: System-wide plugins directory
   cp -r dbs_proxysql_admin ~/.mysqlsh/plugins/

   # Option 2: Custom path (add to your shell init script)
   export MYSQLSH_USER_CONFIG_HOME=/path/to/config_home   # plugins load from <home>/plugins/
   ```

2. Verify installation:
   ```bash
   mysqlsh --py -e "print(dir(dbs.proxysql.admin))"
   ```

## Configuration

### How a config file is selected

When a command runs, the configuration is resolved in this order:

1. An explicit `config_path` argument passed to the command
2. The **active config** set with `dbs.proxysql.admin.useConfig()` (session scoped)
3. Path specified in the `PROXYSQL_SYNC_CONFIG` environment variable
4. `~/.proxysql_config.ini`
5. `/etc/proxysql_sync.conf`
6. `./proxysql_config.ini` (current directory)

`dbs.proxysql.admin.status()` shows which config is currently in effect, and
every sync result includes a `config_source` field so it is always clear which
ProxySQL server was targeted.

### Example Configuration File

```ini
[proxysql]
host = 127.0.0.1
port = 6032
user = radmin
password = radmin
default_hostgroup = 0
excluded_users = root, admin, mysql.sys, mysql.session, mysql.infoschema
required_host = %
```

### Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `host` | ProxySQL admin interface host | 127.0.0.1 |
| `port` | ProxySQL admin interface port | 6032 |
| `user` | ProxySQL admin username (must be remote-capable, see below) | admin |
| `password` | ProxySQL admin password | admin |
| `default_hostgroup` | Default hostgroup for new users | 0 |
| `excluded_users` | Comma-separated list of MySQL users to exclude | root, admin, mysql.sys, etc. |
| `required_host` | mysql.user `Host` of the accounts to sync (exact match) | `%` |

Files created by `dbs.proxysql.admin.createConfig()` are written with `0600`
permissions because they contain the ProxySQL admin password.

### Configuration validation

Config files are validated strictly when loaded, and a broken file fails fast
with a single error that lists **every** problem found — the file that was
used, missing or empty required options (`host`, `port`, `user`, `password`),
malformed values (e.g. a non-numeric `port`), and unknown option names (with a
"did you mean" suggestion for typos such as `requird_host`). Unknown options
are a hard error — the `[proxysql]` section accepts exactly the options listed
above, nothing else. Optional keys (`default_hostgroup`, `excluded_users`,
`required_host`) fall back to their defaults when omitted.

Comments are allowed as full lines starting with `#` or `;`. Inline comments
after a value are **not** supported — they become part of the value (passwords
may legally contain `#` and `;`, so trailing text cannot be stripped) and will
be rejected by validation on typed options like `port`. A `[DEFAULT]` section
and any section other than `[proxysql]` are also rejected.

When the interactive shell offers to recreate a broken config with the wizard,
the previous file is first backed up to `<file>.bak` so existing credentials
are never lost.

### Failure handling during sync

Changes to ProxySQL's `mysql_users` are applied in two steps, **persist first,
then publish**: `SAVE MYSQL USERS TO DISK` runs before `LOAD MYSQL USERS TO
RUNTIME`. If a statement fails mid-batch, the pending changes are discarded
from the admin memory layer (`SAVE MYSQL USERS FROM RUNTIME`, retried on a
fresh connection if needed) so a later manual `LOAD ... TO RUNTIME` cannot
publish a half-applied batch. If the disk save fails, nothing goes live. If
the disk save succeeds but the runtime load fails, the changes are staged
consistently on disk and in memory but are **not live** — a loud warning tells
the operator to run `LOAD MYSQL USERS TO RUNTIME` manually (they would
otherwise activate on the next ProxySQL restart). Avoid running syncs while
another admin session has unsaved edits staged in `mysql_users`: the discard
step copies the whole runtime table back over the memory layer. In the interactive shell, a broken config triggers an
offer to recreate the file with the wizard on the spot; otherwise fix the file
by hand or run `dbs.proxysql.admin.createConfig()` to rebuild it from scratch.
Note that a broken file at a default search location is reported as an error —
it is never silently skipped in favor of the next location, and a
`PROXYSQL_SYNC_CONFIG` variable pointing to a missing file is also an error.

### The `required_host` option

MySQL accounts are keyed by *(User, Host)*: `'app'@'%'` and `'app'@'10.%'` are
two different accounts that can hold two different passwords, while ProxySQL's
`mysql_users` table is keyed by username alone. `required_host` picks which
host row is synchronized so that the password written to ProxySQL is always
deterministic. Only accounts whose `Host` **exactly equals** `required_host`
are synced (no pattern matching is applied); accounts on other hosts are
ignored by `userSync` / `updatePasswords`.

Notes and edge cases:

- **Changing `required_host` on an existing setup can cause password
  mismatches.** ProxySQL entries synced under the previous value keep the old
  host row's passwords until the next `userSync` / `updatePasswords` run, which
  then overwrites them with the new host row's passwords. If the two host rows
  hold different passwords, applications authenticating through ProxySQL with
  the old password will start failing. Compare both host rows in `mysql.user`
  before changing this value.
- `deleteOrphans` is intentionally **not** restricted by `required_host`: a
  ProxySQL user is only deleted when no `mysql.user` account with that username
  exists on *any* host. Users listed in `excluded_users` are never deleted.
- Only `mysql_native_password` and `caching_sha2_password` accounts are synced;
  accounts using other authentication plugins (e.g. `auth_socket`) are skipped
  because their `authentication_string` is not a password hash ProxySQL can
  use.

### ProxySQL admin must accept remote connections

By default, ProxySQL's `admin` account (the first entry in
`admin-admin_credentials`) can **only connect from localhost (127.0.0.1)**. The
plugin runs inside MySQL Shell and connects to ProxySQL over the network — and
with Docker port mapping the connection arrives from the bridge gateway, which
ProxySQL treats as non-local. Using the bare default `admin` account therefore
fails with:

```
MySQL Error 1040 (42000): User 'admin' can only connect locally
```

Add a **remote-capable** admin credential and point the plugin's `user` /
`password` at it. Connect to the ProxySQL admin interface locally (for example
`docker exec <proxysql> mysql -uadmin -padmin -h127.0.0.1 -P6032`) and run:

```sql
SET admin-admin_credentials='admin:admin;radmin:radmin';
LOAD ADMIN VARIABLES TO RUNTIME;
SAVE ADMIN VARIABLES TO DISK;
```

The first pair (`admin:admin`) stays local-only; any additional pair (here
`radmin:radmin`) is allowed to connect remotely. Set `user = radmin` and
`password = radmin` in the config file the plugin uses.

## Usage

### Interactive Shell Mode

Start MySQL Shell and connect to your MySQL server:

```bash
mysqlsh root@localhost:3306
```

Then use the plugin commands (JavaScript/`userSync` spelling; in `\py` use `user_sync`):

```javascript
// Full user sync (insert + update)
dbs.proxysql.admin.userSync()

// Use a specific config file for one call
dbs.proxysql.admin.userSync("/path/to/config.ini")

// Update only passwords for existing users
dbs.proxysql.admin.updatePasswords()

// Delete ProxySQL users not in MySQL
dbs.proxysql.admin.deleteOrphans()

// Reload configuration and verify connection
dbs.proxysql.admin.reloadConfig()
```

### Choosing a config and creating new ones

```javascript
// Show which config is active and which ProxySQL it points to
dbs.proxysql.admin.status()

// Create a config file (interactive wizard when run with no arguments)
dbs.proxysql.admin.createConfig()

// Or create one non-interactively
dbs.proxysql.admin.createConfig("/etc/proxysql/service.ini",
                                "10.0.0.5", 6032, "radmin", "radmin")

// Set the active config for this session
dbs.proxysql.admin.useConfig("/etc/proxysql/service.ini")

// Clear the active config (fall back to the default search)
dbs.proxysql.admin.clearConfig()

// Show the default config search paths
dbs.proxysql.admin.getConfigPath()
```

### Working with several ProxySQL servers

Keep one `.ini` per ProxySQL server — for example one that syncs service
accounts and another that syncs user accounts. Each file carries its own
`excluded_users` filter, so switching the active config switches both the
target server and which users get synced:

```javascript
dbs.proxysql.admin.useConfig("/etc/proxysql/service_accounts.ini")
dbs.proxysql.admin.userSync()          // syncs to the service-accounts ProxySQL

dbs.proxysql.admin.useConfig("/etc/proxysql/user_accounts.ini")
dbs.proxysql.admin.userSync()          // syncs to the user-accounts ProxySQL
```

The active config is **session scoped** and resets when MySQL Shell restarts.
On a fresh install, running a sync command interactively offers to create the
first configuration with the wizard.

### Command Line Mode

```bash
# Sync users
mysqlsh root@localhost:3306 -- dbs proxysql admin userSync

# With a specific config
mysqlsh root@localhost:3306 -- dbs proxysql admin userSync "/path/to/config.ini"

# Update passwords / delete orphans
mysqlsh root@localhost:3306 -- dbs proxysql admin updatePasswords
mysqlsh root@localhost:3306 -- dbs proxysql admin deleteOrphans

# Create a config non-interactively
mysqlsh -- dbs proxysql admin createConfig --config-path /etc/proxysql/service.ini \
    --host 10.0.0.5 --port 6032 --user radmin --password radmin

# Show current status
mysqlsh root@localhost:3306 -- dbs proxysql admin status
```

### Legacy API (deprecated)

The pre-1.0 factory API still works so existing scripts keep running. It returns
an instance bound to the configuration loaded at `create()` time:

```python
\py
proxysql = dbs_proxysql_admin.create()          # or .create("/path/to/config.ini")
proxysql.userSync()
proxysql.updatePasswords()
proxysql.deleteOrphans()
proxysql.reloadConfig()
```

New code should prefer the `dbs.proxysql.admin.*` commands. See
[Migrating from v0.9.x](#migrating-from-v09x-breaking-changes).

## Migrating from v0.9.x (breaking changes)

The configuration file format is **unchanged** — your existing
`proxysql_config.ini` works as-is. The API surface changed:

| v0.9.x | v1.0 |
|--------|------|
| `proxysql = dbs_proxysql_admin.create()` | not required — call commands directly |
| `proxysql.userSync()` | `dbs.proxysql.admin.userSync()` |
| `proxysql.updatePasswords()` | `dbs.proxysql.admin.updatePasswords()` |
| `proxysql.deleteOrphans()` | `dbs.proxysql.admin.deleteOrphans()` |
| `proxysql.reloadConfig()` | `dbs.proxysql.admin.reloadConfig()` |

What changed and why:

- **Object renamed**: the command API moved from the top-level
  `dbs_proxysql_admin` object to `dbs.proxysql.admin`, under the shared `dbs`
  brand namespace. ProxySQL™ is a trademark of ProxySQL LLC, so the plugin does
  not claim a bare `proxysql` global.
- **No instantiation**: there is no `.create()` step in the new API. `config_path`
  is passed per call, or selected once for the session with `useConfig()`.
- **Return values**: the new commands return structured dicts
  (`{success, message, config_source, …}`). The legacy `create()` methods still
  return the original raw shape (e.g. `{count, inserted, updated}`).
- **New capabilities**: CLI support (`mysqlsh -- dbs proxysql admin …`), the
  active-config pointer (`useConfig`/`clearConfig`/`status`), and the config
  wizard (`createConfig`).

Backward compatibility: `dbs_proxysql_admin.create()` is **kept but deprecated**.
Existing scripts continue to work unchanged; migrate when convenient.

## API Reference

The signatures below use the JavaScript/CLI spelling; in `\py` use the
snake_case function name (`userSync` → `user_sync`, etc.).

### `dbs.proxysql.admin.userSync(config_path=None)`

Perform a full user sync from MySQL to ProxySQL.

- **Inserts** new users from MySQL into ProxySQL
- **Updates** passwords for existing users that have changed
- **Does NOT delete** any users from ProxySQL

**Parameters:**
- `config_path` (str, optional): Path to configuration file. If omitted, the active config is used, then the default search.

**Returns:**
```python
{
    "success": True/False,
    "message": "Status message",
    "users_synced": <int>,
    "config_source": <path of the config that was used>
}
```

### `dbs.proxysql.admin.updatePasswords(config_path=None)`

Update passwords in ProxySQL for users that exist in both systems.

**Returns:** `{success, message, passwords_updated, config_source}`

### `dbs.proxysql.admin.deleteOrphans(config_path=None)`

Delete users from ProxySQL that no longer exist in MySQL. A user is only
considered an orphan when no `mysql.user` account with that username exists on
*any* host. Users listed in `excluded_users` are never deleted.

**Returns:** `{success, message, users_deleted, config_source}`

### `dbs.proxysql.admin.reloadConfig(config_path=None)`

Reload configuration and verify ProxySQL connectivity.

**Returns:** `{success, message, config_source}`

### `dbs.proxysql.admin.status()`

Show which configuration is currently in effect.

**Returns:**
```python
{
    "active_config": <path or None>,
    "config_in_use": "active" | "default-search" | "none",
    "config_source": <path>,
    "proxysql": "host:port",
    "proxysql_user": <str>,
    "default_hostgroup": <int>,
    "excluded_users": [ ... ],
    "required_host": <str>,
    "mysql_session_connected": True/False
}
```

### `dbs.proxysql.admin.useConfig(config_path)`

Set the active ProxySQL configuration for the current shell session. Subsequent
commands called without an explicit `config_path` use it. Session scoped — it
resets when MySQL Shell restarts.

**Returns:** `{success, message, config_source, proxysql}`

### `dbs.proxysql.admin.clearConfig()`

Clear the active configuration so commands fall back to the default search.

**Returns:** `{success, message}`

### `dbs.proxysql.admin.createConfig(config_path=None, host=None, port=None, user=None, password=None, default_hostgroup=None, excluded_users=None, required_host=None)`

Create a configuration file. In the interactive shell, omitted values are
prompted for (the password input is hidden); provide any argument to skip that
question. Use it to create the first default config or additional per-server
profiles. The file is written with `0600` permissions.

**Returns:** `{success, message, config_source, proxysql, hint}`

### `dbs.proxysql.admin.getConfigPath()`

Get the list of paths where configuration files are searched.

**Returns:** `{paths: [...], environment_var: "PROXYSQL_SYNC_CONFIG"}`

### `dbs_proxysql_admin.create(config_path=None)` (legacy)

Deprecated factory that returns an extension object with `userSync()`,
`updatePasswords()`, `deleteOrphans()` and `reloadConfig()` methods. Kept for
backward compatibility; prefer the `dbs.proxysql.admin.*` commands.

## Requirements

- MySQL Shell 8.0.21 or later
- ProxySQL 2.x with admin interface enabled
- MySQL 5.7+ or MySQL 8.0+

## Troubleshooting

### "No active MySQL session"

You must connect to a MySQL server before using the plugin:

```bash
mysqlsh root@localhost:3306
```

Or in interactive mode:

```python
\connect root@localhost:3306
```

### "User 'admin' can only connect locally"

ProxySQL's default `admin` account is restricted to localhost. Configure a
remote-capable admin credential and use it in your config file — see
[ProxySQL admin must accept remote connections](#proxysql-admin-must-accept-remote-connections).

### "Failed to connect to ProxySQL"

Check your configuration:
1. Verify the ProxySQL admin interface is running on the configured host/port
2. Check the credentials in the configuration file
3. Ensure the ProxySQL admin user is allowed to connect remotely (above)

### "No ProxySQL config found"

Create one with the wizard:

```javascript
dbs.proxysql.admin.createConfig()
```

…or write a file in a default location manually:

```bash
cat > ~/.proxysql_config.ini << 'EOF'
[proxysql]
host = 127.0.0.1
port = 6032
user = radmin
password = radmin
default_hostgroup = 0
EOF
```

…or point the environment variable at your file:

```bash
export PROXYSQL_SYNC_CONFIG=/path/to/your/config.ini
```

## License

GPL-2.0 License - See LICENSE file for details.
