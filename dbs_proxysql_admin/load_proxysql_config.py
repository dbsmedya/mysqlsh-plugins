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

"""Configuration loader for ProxySQL Admin Plugin.

This module provides functions to load ProxySQL configuration from
various sources including files and environment variables.
"""

import os
import configparser
import difflib
from pathlib import Path
from typing import Dict, Any, List, Optional, Union


class ConfigValidationError(ValueError):
    """Raised when a ProxySQL configuration file fails strict validation.

    The message names the file, lists every problem found and tells the user
    how to recover (fix the file or recreate it with the wizard).
    """

# Default paths to search for configuration files
DEFAULT_PATHS: List[Path] = [
    Path.home() / ".proxysql_config.ini",
    Path("/etc/proxysql_sync.conf"),
    Path.cwd() / "proxysql_config.ini"
]

# Preferred location for newly created configuration files (user writable).
DEFAULT_WRITE_PATH: Path = Path.home() / ".proxysql_config.ini"

# Environment variable name for custom config path
ENV_CONFIG_VAR = "PROXYSQL_SYNC_CONFIG"

# Default configuration values
DEFAULT_CONFIG = {
    "host": "127.0.0.1",
    "port": 6032,
    "user": "admin",
    "password": "admin",
    "default_hostgroup": 0,
    "excluded_users": ['root', 'admin', 'mysql.sys', 'mysql.session', 'mysql.infoschema'],
    "required_host": "%"
}


# Connection options that must be present and non-empty.
REQUIRED_OPTIONS = ("host", "port", "user", "password")

# Behavioral options that fall back to DEFAULT_CONFIG when omitted.
OPTIONAL_OPTIONS = ("default_hostgroup", "excluded_users", "required_host")

# Integer options with their allowed (min, max) range; max None = unbounded.
_INT_OPTIONS = {"port": (1, 65535), "default_hostgroup": (0, None)}

_WIZARD_HINT = (
    "Fix the file, or recreate it from scratch with the wizard: "
    "dbs.proxysql.admin.createConfig()"
)


def _make_parser() -> configparser.ConfigParser:
    """Create the parser used for all config I/O.

    Interpolation must stay disabled: required_host defaults to '%' and
    passwords may contain '%', which BasicInterpolation rejects as syntax.
    """
    return configparser.ConfigParser(interpolation=None)


def _validation_error(path, problems: List[str]) -> ConfigValidationError:
    lines = [f"Invalid ProxySQL configuration: {path}"]
    lines.extend(f"  - {problem}" for problem in problems)
    lines.append(_WIZARD_HINT)
    return ConfigValidationError("\n".join(lines))


def _parse_and_validate(path: Path) -> Dict[str, Any]:
    """Parse a config file, validating it strictly.

    Every problem is collected so the user sees the full list at once.

    Raises:
        ConfigValidationError: If the file is not valid INI, lacks the
            [proxysql] section, misses a required option, contains an empty
            or malformed value, or contains an unknown option.
    """
    parser = _make_parser()
    try:
        parser.read(path)
    except configparser.Error as e:
        raise _validation_error(path, [f"not a valid INI file: {e}"]) from e

    if "proxysql" not in parser:
        raise _validation_error(
            path, ["missing the [proxysql] section that must hold all options"])

    cfg = parser["proxysql"]
    known = set(REQUIRED_OPTIONS) | set(OPTIONAL_OPTIONS)
    problems: List[str] = []

    default_keys = set(parser.defaults())
    if default_keys:
        problems.append(
            "the [DEFAULT] section is not supported; "
            "put all options under [proxysql]")
    for section in parser.sections():
        if section != "proxysql":
            problems.append(
                f"unknown section [{section}]; only [proxysql] is allowed")

    for key in cfg:
        if key in default_keys:
            continue
        if key not in known:
            match = difflib.get_close_matches(key, known, n=1)
            hint = f" (did you mean '{match[0]}'?)" if match else ""
            problems.append(f"unknown option '{key}'{hint}")

    for key in REQUIRED_OPTIONS:
        if key not in cfg:
            problems.append(f"missing required option: {key}")
        elif not cfg.get(key).strip():
            problems.append(f"required option is empty: {key}")

    for key, (low, high) in _INT_OPTIONS.items():
        if key not in cfg:
            continue
        raw = cfg.get(key, "").strip()
        if not raw:
            if key not in REQUIRED_OPTIONS:
                problems.append(f"{key} must not be empty when set")
        else:
            try:
                value = int(raw)
            except ValueError:
                problems.append(f"invalid value for {key}: '{raw}' is not an integer")
            else:
                if value < low or (high is not None and value > high):
                    upper = f" and {high}" if high is not None else " or greater"
                    problems.append(
                        f"invalid value for {key}: {value} must be between "
                        f"{low}{upper}")

    if "required_host" in cfg and not cfg.get("required_host").strip():
        problems.append("required_host must not be empty when set")

    if problems:
        raise _validation_error(path, problems)

    excluded_users_str = cfg.get("excluded_users", "")
    excluded_users = [
        u.strip() for u in excluded_users_str.split(",")
        if u.strip()
    ] if excluded_users_str else DEFAULT_CONFIG["excluded_users"].copy()

    return {
        "host": cfg.get("host"),
        "port": cfg.getint("port"),
        "user": cfg.get("user"),
        "password": cfg.get("password"),
        "default_hostgroup": cfg.getint(
            "default_hostgroup", DEFAULT_CONFIG["default_hostgroup"]),
        "excluded_users": excluded_users,
        "required_host": cfg.get(
            "required_host", DEFAULT_CONFIG["required_host"]),
        "_source": str(path)
    }


def load_proxysql_config() -> Dict[str, Any]:
    """Load ProxySQL configuration from environment or default paths.

    Searches for configuration files in the following order:
    1. Path specified in PROXYSQL_SYNC_CONFIG environment variable
    2. ~/.proxysql_config.ini
    3. /etc/proxysql_sync.conf
    4. ./proxysql_config.ini

    The first existing file is THE configuration: if it is invalid the load
    fails fast with a full list of problems instead of silently falling
    through to the next location.

    Returns:
        Dictionary containing configuration values with keys:
            - host: ProxySQL admin interface host
            - port: ProxySQL admin interface port
            - user: ProxySQL admin username
            - password: ProxySQL admin password
            - default_hostgroup: Default hostgroup for new users
            - excluded_users: List of MySQL users to exclude from sync
            - required_host: mysql.user Host of the accounts to sync
            - _source: Path of the configuration file used

    Raises:
        FileNotFoundError: If no configuration file is found in any location,
            or if PROXYSQL_SYNC_CONFIG points to a non-existent file.
        ConfigValidationError: If the selected file fails validation.

    Example:
        >>> cfg = load_proxysql_config()
        >>> print(f"Connecting to {cfg['host']}:{cfg['port']}")
    """
    custom_path = os.getenv(ENV_CONFIG_VAR)
    if custom_path:
        path = Path(custom_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(
                f"{ENV_CONFIG_VAR} points to a file that does not exist: {path}")
        return _parse_and_validate(path)

    for path in DEFAULT_PATHS:
        if path.exists():
            return _parse_and_validate(path)

    raise FileNotFoundError(
        f"No ProxySQL config found. Searched in: {[str(p) for p in DEFAULT_PATHS]}.\n"
        f"Set the {ENV_CONFIG_VAR} environment variable, or create a config "
        f"with the wizard: dbs.proxysql.admin.createConfig()"
    )


def load_proxysql_config_from(path: Union[str, Path]) -> Dict[str, Any]:
    """Load ProxySQL configuration from a specific file path.

    Args:
        path: Path to the configuration file.

    Returns:
        Dictionary containing configuration values. See load_proxysql_config()
        for details on the dictionary structure.

    Raises:
        FileNotFoundError: If the specified file does not exist.
        ConfigValidationError: If the file fails validation (invalid INI,
            missing [proxysql] section, missing/empty/malformed required
            options, or unknown options).

    Example:
        >>> cfg = load_proxysql_config_from("/etc/myapp/proxysql.conf")
        >>> print(f"Host: {cfg['host']}")
    """
    path = Path(path).expanduser()

    if not path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {path}\n{_WIZARD_HINT}")

    return _parse_and_validate(path)


def get_config_search_paths() -> List[Path]:
    """Get the list of paths where configuration files are searched.

    Returns:
        List of Path objects representing search locations.
    """
    custom_path = os.getenv(ENV_CONFIG_VAR)
    paths: List[Path] = []

    if custom_path:
        paths.append(Path(custom_path).expanduser())

    paths.extend(DEFAULT_PATHS)
    return paths


def find_existing_config() -> Optional[Path]:
    """Return the first existing configuration file, or None if none exist.

    Searches the same locations as load_proxysql_config(). The file is not
    validated here — callers loading it get strict validation.

    Returns:
        The Path of the first existing config file, or None.

    Raises:
        FileNotFoundError: If PROXYSQL_SYNC_CONFIG is set but points to a
            non-existent file (matching load_proxysql_config's behavior).
    """
    custom_path = os.getenv(ENV_CONFIG_VAR)
    if custom_path:
        path = Path(custom_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(
                f"{ENV_CONFIG_VAR} points to a file that does not exist: {path}")
        return path

    for path in DEFAULT_PATHS:
        if path.exists():
            return path
    return None


def save_proxysql_config(path: Union[str, Path], values: Dict[str, Any]) -> str:
    """Write configuration values to an INI file in the [proxysql] section.

    Args:
        path: Destination file path.
        values: Mapping with host, port, user, password, default_hostgroup and
            excluded_users (a list or a comma separated string).

    Returns:
        The absolute path of the written file as a string.
    """
    target = Path(path).expanduser()

    excluded = values.get("excluded_users", DEFAULT_CONFIG["excluded_users"])
    if isinstance(excluded, (list, tuple)):
        excluded = ", ".join(str(u) for u in excluded)

    parser = _make_parser()
    parser["proxysql"] = {
        "host": str(values.get("host", DEFAULT_CONFIG["host"])),
        "port": str(values.get("port", DEFAULT_CONFIG["port"])),
        "user": str(values.get("user", DEFAULT_CONFIG["user"])),
        "password": str(values.get("password", DEFAULT_CONFIG["password"])),
        "default_hostgroup": str(
            values.get("default_hostgroup", DEFAULT_CONFIG["default_hostgroup"])
        ),
        "excluded_users": excluded,
        "required_host": str(
            values.get("required_host", DEFAULT_CONFIG["required_host"])),
    }

    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w") as fh:
        parser.write(fh)

    # The file holds an admin password, so restrict it to the owner.
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass

    return str(target)
