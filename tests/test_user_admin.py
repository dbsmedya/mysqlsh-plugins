"""Behavioral tests for UserAdmin's writes to ProxySQL's mysql_users table."""

import pytest

NATIVE = "mysql_native_password"
SHA2 = "caching_sha2_password"

HASH_A = "AA11"
HASH_B = "BB22"


class TestDeleteOrphans:
    def test_keeps_excluded_users(self, env):
        # 'root' is on the default excluded_users list and present in
        # ProxySQL; it must never be treated as an orphan.
        admin, px = env(
            mysql_users=[("app1", "%", HASH_A, NATIVE)],
            px_users={"app1": HASH_A, "root": HASH_B, "gone": HASH_B},
        )
        result = admin.delete_orphans()

        assert result["count"] == 1
        deleted = [args[0] for _, args in px.writes("DELETE")]
        assert deleted == ["gone"]
        assert "root" in px.table

    def test_keeps_users_existing_under_any_host_or_without_password(self, env):
        # appB exists only at 10.% (not the synced host) and appC has no
        # password hash; both still exist in mysql.user, so neither is an
        # orphan.
        admin, px = env(
            mysql_users=[
                ("appB", "10.%", HASH_A, NATIVE),
                ("appC", "%", "", NATIVE),
            ],
            px_users={"appB": HASH_A, "appC": HASH_B},
        )
        result = admin.delete_orphans()

        assert result["count"] == 0
        assert px.writes("DELETE") == []
        assert px.admin_commands() == []


class TestRequiredHostSelection:
    def test_user_sync_writes_the_required_host_password(self, env):
        # Same user on two hosts with different passwords: the row matching
        # required_host (default '%') must win, deterministically.
        admin, px = env(
            mysql_users=[
                ("app", "%", HASH_A, NATIVE),
                ("app", "localhost", HASH_B, NATIVE),
            ],
            px_users={},
        )
        result = admin.user_sync()

        assert result["inserted"] == 1
        inserts = px.writes("INSERT")
        assert len(inserts) == 1
        assert inserts[0][1][:2] == ["app", HASH_A]

    def test_update_passwords_uses_the_required_host_row(self, env):
        admin, px = env(
            mysql_users=[
                ("app", "%", HASH_A, NATIVE),
                ("app", "localhost", HASH_B, NATIVE),
            ],
            px_users={"app": "OLD0"},
        )
        result = admin.update_passwords()

        assert result["count"] == 1
        updates = px.writes("UPDATE")
        assert updates[0][1] == [HASH_A, "app"]

    def test_user_sync_skips_hosts_not_matching_required_host(self, env):
        admin, px = env(
            mysql_users=[("svc", "10.%", HASH_A, NATIVE)],
            px_users={},
        )
        result = admin.user_sync()

        assert result["count"] == 0
        assert px.writes("INSERT") == []

    def test_required_host_is_configurable(self, env):
        admin, px = env(
            mysql_users=[
                ("svc", "10.%", HASH_A, NATIVE),
                ("svc", "%", HASH_B, NATIVE),
            ],
            px_users={},
            required_host="10.%",
        )
        admin.user_sync()

        inserts = px.writes("INSERT")
        assert len(inserts) == 1
        assert inserts[0][1][:2] == ["svc", HASH_A]


class TestAuthPluginFilter:
    def test_unsupported_plugins_are_not_synced(self, env):
        # auth_socket stores the OS user name in authentication_string; it
        # must never land in mysql_users as a password.
        admin, px = env(
            mysql_users=[
                ("sockuser", "%", "6F73757365720A", "auth_socket"),
                ("nativeuser", "%", HASH_A, NATIVE),
                ("sha2user", "%", HASH_B, SHA2),
            ],
            px_users={},
        )
        result = admin.user_sync()

        assert result["inserted"] == 2
        inserted = sorted(args[0] for _, args in px.writes("INSERT"))
        assert inserted == ["nativeuser", "sha2user"]


class TestApplyOrdering:
    """SAVE MYSQL USERS TO DISK must always run before LOAD TO RUNTIME."""

    def test_save_to_disk_runs_before_load_to_runtime(self, env):
        admin, px = env(
            mysql_users=[("app", "%", HASH_A, NATIVE)],
            px_users={},
        )
        admin.user_sync()

        commands = px.admin_commands()
        assert commands.index("SAVE MYSQL USERS TO DISK") < \
            commands.index("LOAD MYSQL USERS TO RUNTIME")

    def test_save_failure_rolls_back_and_nothing_goes_live(self, env):
        admin, px = env(
            mysql_users=[("app", "%", HASH_A, NATIVE)],
            px_users={},
            fail_on=("SAVE MYSQL USERS TO DISK", 1),
        )
        with pytest.raises(Exception, match="simulated ProxySQL failure"):
            admin.user_sync()

        commands = px.admin_commands()
        assert "LOAD MYSQL USERS TO RUNTIME" not in commands
        assert "SAVE MYSQL USERS FROM RUNTIME" in commands

    def test_load_failure_after_save_warns_loudly_and_keeps_staged(
            self, env, capsys):
        # Changes persisted to disk must NOT be rolled back out of memory;
        # the operator finishes the publish step manually.
        admin, px = env(
            mysql_users=[("app", "%", HASH_A, NATIVE)],
            px_users={},
            fail_on=("LOAD MYSQL USERS TO RUNTIME", 1),
        )
        with pytest.raises(Exception, match="LOAD MYSQL USERS TO RUNTIME"):
            admin.user_sync()

        assert "SAVE MYSQL USERS FROM RUNTIME" not in px.admin_commands()
        out = capsys.readouterr().out
        assert "WARNING" in out
        assert "LOAD MYSQL USERS TO RUNTIME" in out


class TestPartialFailureRollback:
    def assert_rolled_back(self, px):
        # SAVE ... FROM RUNTIME is the runtime->memory copy; the intuitive
        # "LOAD ... FROM RUNTIME" is a syntax error in ProxySQL's admin
        # grammar (verified against a live ProxySQL 2.x).
        commands = px.admin_commands()
        assert "SAVE MYSQL USERS FROM RUNTIME" in commands
        assert "LOAD MYSQL USERS TO RUNTIME" not in commands
        assert "SAVE MYSQL USERS TO DISK" not in commands

    def test_user_sync_rolls_back_memory_layer(self, env):
        admin, px = env(
            mysql_users=[
                ("u1", "%", HASH_A, NATIVE),
                ("u2", "%", HASH_B, NATIVE),
            ],
            px_users={},
            fail_on=("INSERT", 2),
        )
        with pytest.raises(Exception, match="simulated ProxySQL failure"):
            admin.user_sync()
        self.assert_rolled_back(px)

    def test_update_passwords_rolls_back_memory_layer(self, env):
        admin, px = env(
            mysql_users=[
                ("u1", "%", HASH_A, NATIVE),
                ("u2", "%", HASH_B, NATIVE),
            ],
            px_users={"u1": "OLD0", "u2": "OLD0"},
            fail_on=("UPDATE", 2),
        )
        with pytest.raises(Exception, match="simulated ProxySQL failure"):
            admin.update_passwords()
        self.assert_rolled_back(px)

    def test_delete_orphans_rolls_back_memory_layer(self, env):
        admin, px = env(
            mysql_users=[("app", "%", HASH_A, NATIVE)],
            px_users={"app": HASH_A, "gone1": HASH_B, "gone2": HASH_B},
            fail_on=("DELETE", 2),
        )
        with pytest.raises(Exception, match="simulated ProxySQL failure"):
            admin.delete_orphans()
        self.assert_rolled_back(px)

    def test_rollback_retries_on_a_fresh_session_when_connection_dies(
            self, env):
        import mysqlsh
        from tests.conftest import FakeProxySQLSession

        admin, px = env(
            mysql_users=[
                ("u1", "%", HASH_A, NATIVE),
                ("u2", "%", HASH_B, NATIVE),
            ],
            px_users={},
            fail_on=("INSERT", 2),
            die_on_fail=True,
        )
        fresh = FakeProxySQLSession({})
        mysqlsh.globals.shell.sessions.append(fresh)

        with pytest.raises(Exception, match="simulated ProxySQL failure"):
            admin.user_sync()

        assert "SAVE MYSQL USERS FROM RUNTIME" in fresh.admin_commands()
        assert fresh.closed

    def test_rollback_failure_warns_loudly(self, env, capsys):
        # Both the dead session and the reconnect attempt fail: the operator
        # must be told the memory layer still holds the partial batch.
        admin, px = env(
            mysql_users=[
                ("u1", "%", HASH_A, NATIVE),
                ("u2", "%", HASH_B, NATIVE),
            ],
            px_users={},
            fail_on=("INSERT", 2),
            die_on_fail=True,
        )
        with pytest.raises(Exception, match="simulated"):
            admin.user_sync()

        out = capsys.readouterr().out
        assert "WARNING" in out
        assert "SAVE MYSQL USERS FROM RUNTIME" in out


class TestExistingBehaviorGuards:
    """Regression guards for behavior that was already correct."""

    def test_excluded_users_are_not_synced(self, env):
        admin, px = env(
            mysql_users=[
                ("root", "%", HASH_A, NATIVE),
                ("app", "%", HASH_B, NATIVE),
            ],
            px_users={},
        )
        result = admin.user_sync()

        assert result["inserted"] == 1
        assert [args[0] for _, args in px.writes("INSERT")] == ["app"]

    def test_no_writes_means_no_runtime_reload(self, env):
        admin, px = env(
            mysql_users=[("app", "%", HASH_A, NATIVE)],
            px_users={"app": HASH_A},
        )
        result = admin.user_sync()

        assert result["count"] == 0
        assert px.admin_commands() == []
