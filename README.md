# DBS MySQL Shell Plugins

MySQL Shell plugins maintained by [DBS Medya](https://dbsmedya.com).

## Plugin architecture

MySQL Shell plugins are Python packages that the shell auto-loads from
`<user-config-home>/plugins/`. Each plugin is a self-contained folder with an
`__init__.py` bootstrap and an `init.py` that uses the `@plugin` /
`@plugin_function` decorators to register objects and functions into the shell's
global namespace. The same registered command works identically in the
interactive shell (`\py` / `\js`) and from the command line
(`mysqlsh -- <object> <command> …`); only the function-name casing follows the
active language — snake_case in Python (`user_sync`), camelCase in JavaScript
(`userSync`), while the object path itself reads the same in both.

DBS plugins in this repository share a single top-level `dbs` brand object.
MySQL Shell reuses an existing top-level object when another plugin re-declares
it, so multiple plugin folders can hang branches off the same namespace —
`dbs.proxysql.*` today, `dbs.performance.*` or others later — without any of them
claiming a generic global. The repository also doubles as a MySQL Shell *plugin
repository*: the `mysql-shell-plugins-manifest.json` at the repo root lets users
register it with `plugins.repositories.add('github/dbsmedya/mysqlsh-plugins/')`
and install a plugin with `plugins.install()`, which downloads the versioned
release archive and extracts it into `<user-config-home>/plugins/<moduleName>/`.
Releases are built and published automatically from the `master` branch; `main`
carries development and test features.

## Plugins

### dbs_proxysql_admin

Synchronizes MySQL user accounts into ProxySQL — full sync, password-only
updates, and orphan cleanup — with support for multiple ProxySQL targets (one
config file per server, switchable at runtime) and an interactive setup wizard.
Commands live under `dbs.proxysql.admin` (`userSync`, `updatePasswords`,
`deleteOrphans`, `reloadConfig`, `status`, `useConfig`, `createConfig`, …); the
legacy `dbs_proxysql_admin.create()` factory is kept for backward compatibility.
It has no third-party Python dependencies and syncs `caching_sha2_password`
hashes (ProxySQL ≥ 2.6 / MySQL 8.4 LTS).

📖 **Full documentation:** [dbs_proxysql_admin/README.md](dbs_proxysql_admin/README.md)

## Installing a plugin

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

Restart MySQL Shell after installing. See each plugin's README for configuration
and usage.

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
