# Changelog

The section matching `latestVersion` in `mysql-shell-plugins-manifest.json` is
published as the GitHub release notes by `.github/workflows/release.yml`.

## v1.1.0

Data-integrity and configuration-safety release for `dbs_proxysql_admin`. All
sync paths were reviewed, fixed, and covered by a new test suite (45 tests)
plus live verification against MySQL 8.4 / ProxySQL 2.x.

### Fixed

- **`deleteOrphans` could permanently delete valid ProxySQL users.** A user is
  now an orphan only when no `mysql.user` account with that name exists on
  *any* host, and users on the `excluded_users` list are never deleted.
  Previously, excluded users (e.g. `root`) and accounts without a password
  hash were treated as orphans, deleted from runtime, and persisted to disk.
- **Non-deterministic password sync for multi-host accounts.** When the same
  username existed on several hosts with different passwords, an arbitrary
  host's hash was written to ProxySQL and could flip between runs. The new
  `required_host` option (below) makes the selection deterministic.
- **Half-applied batches could go live later.** A mid-batch failure now
  discards the pending changes from the admin memory layer
  (`SAVE MYSQL USERS FROM RUNTIME`, retried on a fresh connection if the
  original one died), so a later manual `LOAD MYSQL USERS TO RUNTIME` cannot
  publish a partial sync. If the discard is impossible, a loud warning names
  the exact manual command to run.
- **Non-password data can no longer be written into `mysql_users.password`.**
  Only `mysql_native_password` and `caching_sha2_password` accounts are
  synced; plugins like `auth_socket` store non-hash data in
  `authentication_string` and are skipped.
- Passwords containing `%`, `#` or `;` now load correctly from the config
  file (config I/O no longer applies INI interpolation, and inline comments
  are never stripped out of values).

### Changed

- **Apply ordering is now persist-first:** `SAVE MYSQL USERS TO DISK` runs
  before `LOAD MYSQL USERS TO RUNTIME`. A disk failure means nothing went
  live; a runtime-load failure after a successful save leaves the changes
  staged consistently (they activate on the next ProxySQL restart) and warns
  the operator loudly to publish manually.
- **Strict, fail-fast config validation.** A broken `proxysql_config.ini`
  fails immediately with one error listing every problem — missing or empty
  required options (`host`, `port`, `user`, `password`), malformed values,
  unknown options (with "did you mean" hints for typos), unknown sections and
  `[DEFAULT]` sections — plus guidance to fix the file or recreate it with
  `dbs.proxysql.admin.createConfig()`. In the interactive shell the wizard is
  offered on the spot, and a broken file is backed up to `<file>.bak` before
  being recreated.

### Added

- `required_host` config option (default `%`): the `mysql.user` `Host` value
  (exact match) of the accounts to synchronize. See the README for the edge
  case when changing it on an existing setup.
- `createConfig()` accepts a `required_host` argument; `status()` reports it.
- Unit test suite under `tests/` (pytest, no MySQL Shell required).

### Upgrade notes (strictness is intentional)

- Config files that previously "worked" by accident are now rejected with a
  clear error: missing required options no longer silently fall back to
  `admin`/`admin` defaults, and stray keys or sections are hard errors.
- Hand-written pre-1.1 configs that escaped percent signs as `%%` must now
  write a single literal `%`.
- `PROXYSQL_SYNC_CONFIG` pointing at a missing file is now an error instead
  of a silent fallback to the default search paths.
- `sha256_password` accounts are no longer synced (ProxySQL cannot
  authenticate them).
- Sites whose application accounts are not at host `'%'` must set
  `required_host` accordingly — with the default, such accounts are no longer
  synced.

## v1.0.0

- `dbs.proxysql.admin.*` API under the shared `dbs` namespace (`userSync`,
  `updatePasswords`, `deleteOrphans`, `reloadConfig`, `status`, `useConfig`,
  `clearConfig`, `createConfig`, `getConfigPath`), multi-target config
  support, interactive setup wizard, and the legacy
  `dbs_proxysql_admin.create()` compatibility factory.
