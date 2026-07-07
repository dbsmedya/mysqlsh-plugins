# DBS MySQL Shell Plugins

MySQL Shell plugins maintained by [DBS Medya](https://dbsmedya.com).

## Purpose

This repository hosts our MySQL Shell plugins and doubles as a MySQL Shell
**plugin repository**: you can register it once in the shell and install the
plugins from it directly (see [Installation](#installation)).

## Plugin architecture

All plugins in this repository register their commands under a single shared
`dbs` object inside MySQL Shell, one branch per toolset:

```text
dbs
└── proxysql
    └── admin      → userSync, updatePasswords, deleteOrphans, status, …
```

Commands work the same in the interactive shell and from the command line;
only the function-name casing follows the active language:

```text
Python:      dbs.proxysql.admin.user_sync()
JavaScript:  dbs.proxysql.admin.userSync()
Command line: mysqlsh root@localhost:3306 -- dbs proxysql admin userSync
```

Future plugins will add their own branches (for example `dbs.performance.*`)
without claiming any new global names.

## Plugins

| Plugin | Description | Documentation |
|--------|-------------|---------------|
| `dbs_proxysql_admin` | Synchronizes MySQL user accounts into ProxySQL: full sync, password updates, orphan cleanup, multiple ProxySQL targets. | [dbs_proxysql_admin/README.md](dbs_proxysql_admin/README.md) |

## Installation

**From this repository (recommended):**

```js
\js
plugins.repositories.add('github/dbsmedya/mysqlsh-plugins/')
plugins.install()
```

**By cloning:**

```bash
git clone https://github.com/dbsmedya/mysqlsh-plugins.git ~/.mysqlsh/plugins/
```

Restart MySQL Shell after installing. Configuration and usage are covered in
each plugin's own README.

## License

GPL-2.0 — see the [LICENSE](LICENSE) file.

## Trademarks

- MySQL® is a registered trademark of Oracle Corporation and/or its affiliates.
- MariaDB® is a registered trademark of MariaDB Corporation Ab.
- ProxySQL™ is a trademark of ProxySQL LLC.

## Support

Professional MySQL and database consulting services are available at
[dbsmedya.com](https://dbsmedya.com). For bugs and feature requests, open an
issue in this repository.
