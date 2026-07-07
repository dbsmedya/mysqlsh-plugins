"""Tests for strict, fail-fast validation of proxysql_config.ini."""

import pytest

import mysqlsh

import dbs_proxysql_admin.load_proxysql_config as lpc
from dbs_proxysql_admin.load_proxysql_config import (
    ConfigValidationError,
    load_proxysql_config,
    load_proxysql_config_from,
)
from dbs_proxysql_admin import admin_core


def write(path, text):
    path.write_text(text)
    return str(path)


VALID = (
    "[proxysql]\nhost = 127.0.0.1\nport = 6032\n"
    "user = radmin\npassword = radmin\n"
)


class TestStrictValidation:
    def test_missing_required_option_fails_fast_with_guidance(self, tmp_path):
        cfg = write(tmp_path / "c.ini",
                    "[proxysql]\nhost = 127.0.0.1\nport = 6032\nuser = radmin\n")
        with pytest.raises(ConfigValidationError) as exc:
            load_proxysql_config_from(cfg)
        msg = str(exc.value)
        assert "password" in msg
        assert "createConfig" in msg
        assert str(cfg) in msg

    def test_all_problems_reported_in_one_error(self, tmp_path):
        cfg = write(tmp_path / "c.ini",
                    "[proxysql]\nhost = 127.0.0.1\nport = abc\n"
                    "user = radmin\nrequird_host = 10.%\n")
        with pytest.raises(ConfigValidationError) as exc:
            load_proxysql_config_from(cfg)
        msg = str(exc.value)
        assert "password" in msg                  # missing
        assert "'abc'" in msg                     # bad port
        assert "requird_host" in msg              # unknown key
        assert "did you mean 'required_host'" in msg
        assert "createConfig" in msg

    def test_port_out_of_range(self, tmp_path):
        cfg = write(tmp_path / "c.ini",
                    "[proxysql]\nhost = h\nport = 70000\n"
                    "user = u\npassword = p\n")
        with pytest.raises(ConfigValidationError, match="port"):
            load_proxysql_config_from(cfg)

    def test_empty_required_value_is_reported(self, tmp_path):
        cfg = write(tmp_path / "c.ini",
                    "[proxysql]\nhost = h\nport = 6032\n"
                    "user = u\npassword =\n")
        with pytest.raises(ConfigValidationError, match="password"):
            load_proxysql_config_from(cfg)

    def test_missing_section_mentions_section_and_wizard(self, tmp_path):
        cfg = write(tmp_path / "c.ini", "[proxy]\nhost = 127.0.0.1\n")
        with pytest.raises(ConfigValidationError) as exc:
            load_proxysql_config_from(cfg)
        msg = str(exc.value)
        assert "[proxysql]" in msg
        assert "createConfig" in msg

    def test_garbage_file_fails_with_clear_error(self, tmp_path):
        cfg = write(tmp_path / "c.ini", "this is : not { an ini\nfile at all\n")
        with pytest.raises(ConfigValidationError, match="createConfig"):
            load_proxysql_config_from(cfg)

    def test_minimal_valid_config_uses_defaults_for_optional(self, tmp_path):
        cfg = write(tmp_path / "c.ini", VALID)
        loaded = load_proxysql_config_from(cfg)
        assert loaded["default_hostgroup"] == 0
        assert loaded["required_host"] == "%"
        assert "root" in loaded["excluded_users"]

    def test_full_line_comments_are_allowed(self, tmp_path):
        cfg = write(tmp_path / "c.ini",
                    "# ProxySQL connection\n"
                    "; alternative comment style\n"
                    "[proxysql]\n"
                    "# which host to sync\n"
                    "host = 127.0.0.1\n"
                    "port = 6032\n"
                    "user = radmin\n"
                    "password = radmin\n"
                    "; behavioral options\n"
                    "required_host = 10.%\n")
        loaded = load_proxysql_config_from(cfg)
        assert loaded["host"] == "127.0.0.1"
        assert loaded["required_host"] == "10.%"

    def test_inline_comments_are_not_stripped(self, tmp_path):
        # Inline comments must stay disabled: passwords may legally contain
        # '#' or ';'. A trailing comment therefore becomes part of the value
        # and strict validation reports it.
        cfg = write(tmp_path / "c.ini",
                    "[proxysql]\nhost = 127.0.0.1\n"
                    "port = 6032 # admin port\n"
                    "user = radmin\npassword = radmin\n")
        with pytest.raises(ConfigValidationError,
                           match="'6032 # admin port' is not an integer"):
            load_proxysql_config_from(cfg)

    def test_hash_and_semicolon_survive_in_password(self, tmp_path):
        cfg = write(tmp_path / "c.ini",
                    "[proxysql]\nhost = 127.0.0.1\nport = 6032\n"
                    "user = radmin\npassword = se#cr;et\n")
        assert load_proxysql_config_from(cfg)["password"] == "se#cr;et"

    def test_unknown_key_is_a_hard_fail(self, tmp_path):
        # The ini structure is enforced: any option outside the documented
        # set is an error, not a warning.
        cfg = write(tmp_path / "c.ini",
                    VALID + "my_custom_note = hello\n")
        with pytest.raises(ConfigValidationError, match="my_custom_note"):
            load_proxysql_config_from(cfg)

    def test_empty_optional_int_is_a_validation_error(self, tmp_path):
        # 'default_hostgroup =' must be caught by validation, not crash
        # later in cfg.getint() with a raw ValueError.
        cfg = write(tmp_path / "c.ini", VALID + "default_hostgroup =\n")
        with pytest.raises(ConfigValidationError, match="default_hostgroup"):
            load_proxysql_config_from(cfg)

    def test_default_section_is_rejected(self, tmp_path):
        cfg = write(tmp_path / "c.ini",
                    "[DEFAULT]\ntimeout = 5\n" + VALID)
        with pytest.raises(ConfigValidationError, match=r"\[DEFAULT\]"):
            load_proxysql_config_from(cfg)

    def test_unknown_sections_are_rejected(self, tmp_path):
        cfg = write(tmp_path / "c.ini",
                    VALID + "[other_tool]\nkey = value\n")
        with pytest.raises(ConfigValidationError, match=r"\[other_tool\]"):
            load_proxysql_config_from(cfg)


class TestDefaultSearchFailsFast:
    def test_env_var_pointing_to_missing_file_fails(self, tmp_path, monkeypatch):
        monkeypatch.setenv(lpc.ENV_CONFIG_VAR, str(tmp_path / "nope.ini"))
        with pytest.raises(FileNotFoundError, match=lpc.ENV_CONFIG_VAR):
            load_proxysql_config()

    def test_first_existing_invalid_file_is_not_skipped(self, tmp_path, monkeypatch):
        # A broken config must fail loudly, not silently fall through to the
        # next search location.
        broken = tmp_path / "broken.ini"
        write(broken, "[proxysql]\nhost = h\n")
        valid = tmp_path / "valid.ini"
        write(valid, VALID)
        monkeypatch.delenv(lpc.ENV_CONFIG_VAR, raising=False)
        monkeypatch.setattr(lpc, "DEFAULT_PATHS", [broken, valid])
        with pytest.raises(ConfigValidationError, match="broken.ini"):
            load_proxysql_config()


class ScriptedShell:
    """shell.prompt double returning scripted answers, then ''."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.prompts = []

    def prompt(self, message, options=None):
        self.prompts.append(message)
        return self.answers.pop(0) if self.answers else ""


class TestEnsureConfig:
    def test_noninteractive_invalid_config_raises(self, tmp_path):
        cfg = write(tmp_path / "c.ini", "[proxysql]\nhost = h\n")
        with pytest.raises(ConfigValidationError):
            admin_core.ensure_config(cfg, interactive=False)

    def test_interactive_offers_wizard_recreate(self, tmp_path):
        cfg = write(tmp_path / "c.ini", "[proxysql]\nhost = h\nport = abc\n")
        shell = ScriptedShell(["y"])  # accept recreate; defaults for the rest
        mysqlsh.globals.shell = shell

        result = admin_core.ensure_config(cfg, interactive=True)

        assert result == str(cfg)
        reloaded = load_proxysql_config_from(cfg)
        assert reloaded["port"] == 6032
        assert any("Recreate" in p for p in shell.prompts)

    def test_interactive_decline_reraises(self, tmp_path):
        cfg = write(tmp_path / "c.ini", "[proxysql]\nhost = h\n")
        mysqlsh.globals.shell = ScriptedShell(["n"])
        with pytest.raises(ConfigValidationError):
            admin_core.ensure_config(cfg, interactive=True)

    def test_recreate_backs_up_the_broken_file(self, tmp_path):
        broken_content = "[proxysql]\nhost = 10.9.9.9\nport = abc\n"
        cfg = write(tmp_path / "c.ini", broken_content)
        mysqlsh.globals.shell = ScriptedShell(["y"])

        admin_core.ensure_config(cfg, interactive=True)

        backup = tmp_path / "c.ini.bak"
        assert backup.read_text() == broken_content

    def test_stale_env_var_raises_noninteractively(self, tmp_path, monkeypatch):
        monkeypatch.setenv(lpc.ENV_CONFIG_VAR, str(tmp_path / "gone.ini"))
        with pytest.raises(FileNotFoundError, match=lpc.ENV_CONFIG_VAR):
            admin_core.ensure_config(None, interactive=False)

    def test_stale_env_var_offers_wizard_interactively(
            self, tmp_path, monkeypatch):
        env_target = tmp_path / "gone.ini"
        monkeypatch.setenv(lpc.ENV_CONFIG_VAR, str(env_target))
        mysqlsh.globals.shell = ScriptedShell(["y"])

        result = admin_core.ensure_config(None, interactive=True)

        assert result == str(env_target)
        assert load_proxysql_config_from(env_target)["port"] == 6032

    def test_missing_explicit_path_offers_wizard_interactively(self, tmp_path):
        target = tmp_path / "new.ini"
        mysqlsh.globals.shell = ScriptedShell(["y"])

        result = admin_core.ensure_config(str(target), interactive=True)

        assert result == str(target)
        assert load_proxysql_config_from(target)["host"] == "127.0.0.1"


class TestWizardInputValidation:
    def test_wizard_rejects_non_integer_port(self, tmp_path):
        with pytest.raises(ValueError, match="port must be an integer"):
            admin_core.run_config_wizard(
                str(tmp_path / "w.ini"),
                provided={"port": "abc"},
                interactive=False,
            )
