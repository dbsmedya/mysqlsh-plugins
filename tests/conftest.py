"""Shared test fixtures for the dbs_proxysql_admin plugin.

The plugin modules import ``mysqlsh`` at import time, which only exists inside
MySQL Shell. A stub module is installed in ``sys.modules`` before the plugin
package is imported so the code under test runs unmodified.
"""

import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class _ShellGlobals:
    """Mutable stand-in for mysqlsh.globals; tests assign session/shell."""

    session = None
    shell = None


if "mysqlsh" not in sys.modules:
    stub = types.ModuleType("mysqlsh")
    stub.globals = _ShellGlobals()
    sys.modules["mysqlsh"] = stub


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self):
        return self._rows


class FakeMySQLSession:
    """Emulates the mysql.user table for the queries the plugin issues.

    ``users`` is a list of (User, Host, auth_string_hex, plugin) tuples;
    an empty auth_string_hex models an account without a password hash.
    """

    def __init__(self, users):
        self.users = users

    def is_open(self):
        return True

    def run_sql(self, query, args=None):
        assert "mysql.user" in query, f"unexpected MySQL query: {query}"
        has_length_filter = "LENGTH(authentication_string)" in query
        rows = [
            u for u in self.users
            if not has_length_filter or len(u[2]) > 0
        ]
        if "hex(authentication_string)" not in query:
            # Existence-style query: usernames only.
            seen, out = set(), []
            for user, _host, _auth, _plugin in rows:
                if user not in seen:
                    seen.add(user)
                    out.append([user])
            return FakeResult(out)
        if "Host" in query and "plugin" in query:
            return FakeResult(
                [[u, h, a, p] for (u, h, a, p) in rows])
        # Legacy shape: DISTINCT (User, hex(authentication_string)).
        seen, out = set(), []
        for user, _host, auth, _plugin in rows:
            if (user, auth) not in seen:
                seen.add((user, auth))
                out.append([user, auth])
        return FakeResult(out)


class FakeProxySQLSession:
    """Emulates the ProxySQL admin interface's mysql_users table.

    Records every statement in ``statements``. Set ``fail_on`` to a substring
    plus 1-based occurrence count to raise on that write, e.g.
    ``("INSERT", 2)`` fails the second INSERT. With ``die_on_fail`` the
    session behaves like a dropped connection: every statement after the
    simulated failure raises too.
    """

    def __init__(self, users=None, fail_on=None, die_on_fail=False):
        self.table = dict(users or {})
        self.statements = []
        self.fail_on = fail_on
        self.die_on_fail = die_on_fail
        self._fail_seen = 0
        self._dead = False
        self.closed = False

    def close(self):
        self.closed = True

    def _maybe_fail(self, query):
        if self._dead:
            raise Exception("simulated lost connection")
        if self.fail_on and self.fail_on[0] in query:
            self._fail_seen += 1
            if self._fail_seen == self.fail_on[1]:
                if self.die_on_fail:
                    self._dead = True
                raise Exception("simulated ProxySQL failure")

    def run_sql(self, query, args=None):
        self.statements.append((query, list(args) if args else None))
        self._maybe_fail(query)
        if query.startswith("SELECT username, hex(password)"):
            return FakeResult([[u, p] for u, p in self.table.items()])
        if query.startswith("INSERT INTO mysql_users"):
            self.table[args[0]] = args[1]
        elif query.startswith("UPDATE mysql_users"):
            self.table[args[1]] = args[0]
        elif query.startswith("DELETE FROM mysql_users"):
            self.table.pop(args[0], None)
        return FakeResult([])

    def writes(self, kind):
        return [s for s in self.statements if s[0].startswith(kind)]

    def admin_commands(self):
        return [q for q, _ in self.statements if "MYSQL USERS" in q]


class FakeShell:
    """Returns queued sessions in order; the last one is returned forever."""

    def __init__(self, *sessions):
        self.sessions = list(sessions)

    def open_session(self, options):
        if len(self.sessions) > 1:
            return self.sessions.pop(0)
        return self.sessions[0]


@pytest.fixture
def env(tmp_path):
    """Wire fake MySQL/ProxySQL sessions into the mysqlsh stub.

    Returns a factory: env(mysql_users, px_users, fail_on=None, **cfg)
    -> (UserAdmin, FakeProxySQLSession).
    """
    import mysqlsh
    from dbs_proxysql_admin.user_admin import UserAdmin

    def make(mysql_users, px_users, fail_on=None, die_on_fail=False,
             **cfg_overrides):
        px = FakeProxySQLSession(px_users, fail_on=fail_on,
                                 die_on_fail=die_on_fail)
        mysqlsh.globals.session = FakeMySQLSession(mysql_users)
        mysqlsh.globals.shell = FakeShell(px)

        cfg_lines = ["[proxysql]", "host = 127.0.0.1", "port = 6032",
                     "user = radmin", "password = radmin",
                     "default_hostgroup = 10"]
        for key, value in cfg_overrides.items():
            cfg_lines.append(f"{key} = {value}")
        cfg_file = tmp_path / "proxysql_config.ini"
        cfg_file.write_text("\n".join(cfg_lines) + "\n")

        return UserAdmin(config_path=str(cfg_file)), px

    return make
