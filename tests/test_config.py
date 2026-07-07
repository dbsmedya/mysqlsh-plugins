"""Tests for the required_host config field and config round-tripping."""

from dbs_proxysql_admin.load_proxysql_config import (
    DEFAULT_CONFIG,
    load_proxysql_config_from,
    save_proxysql_config,
)


def test_default_config_has_required_host_wildcard():
    assert DEFAULT_CONFIG["required_host"] == "%"


def test_required_host_round_trips_through_save_and_load(tmp_path):
    # '%' is configparser interpolation syntax; it must survive a
    # write/read cycle unescaped.
    path = tmp_path / "cfg.ini"
    save_proxysql_config(path, {
        "host": "10.0.0.5",
        "port": 6032,
        "user": "radmin",
        "password": "radmin",
        "default_hostgroup": 2,
        "excluded_users": ["root"],
        "required_host": "%",
    })
    cfg = load_proxysql_config_from(path)
    assert cfg["required_host"] == "%"


def test_required_host_defaults_when_missing_from_file(tmp_path):
    # Config files written by older plugin versions have no required_host.
    path = tmp_path / "old.ini"
    path.write_text(
        "[proxysql]\nhost = 127.0.0.1\nport = 6032\n"
        "user = radmin\npassword = radmin\n")
    cfg = load_proxysql_config_from(path)
    assert cfg["required_host"] == "%"


def test_percent_sign_in_password_survives(tmp_path):
    path = tmp_path / "pw.ini"
    save_proxysql_config(path, {
        "host": "127.0.0.1",
        "port": 6032,
        "user": "radmin",
        "password": "sec%ret",
        "default_hostgroup": 0,
        "excluded_users": ["root"],
    })
    cfg = load_proxysql_config_from(path)
    assert cfg["password"] == "sec%ret"
