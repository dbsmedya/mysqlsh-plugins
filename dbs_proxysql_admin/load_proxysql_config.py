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
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

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
    "excluded_users": ['root', 'admin', 'mysql.sys', 'mysql.session', 'mysql.infoschema']
}


def load_proxysql_config() -> Dict[str, Any]:
    """Load ProxySQL configuration from environment or default paths.

    Searches for configuration files in the following order:
    1. Path specified in PROXYSQL_SYNC_CONFIG environment variable
    2. ~/.proxysql_config.ini
    3. /etc/proxysql_sync.conf
    4. ./proxysql_config.ini

    Returns:
        Dictionary containing configuration values with keys:
            - host: ProxySQL admin interface host
            - port: ProxySQL admin interface port
            - user: ProxySQL admin username
            - password: ProxySQL admin password
            - default_hostgroup: Default hostgroup for new users
            - excluded_users: List of MySQL users to exclude from sync
            - _source: Path of the configuration file used

    Raises:
        FileNotFoundError: If no configuration file is found in any location.

    Example:
        >>> cfg = load_proxysql_config()
        >>> print(f"Connecting to {cfg['host']}:{cfg['port']}")
    """
    custom_path = os.getenv(ENV_CONFIG_VAR)
    search_paths: List[Path] = []
    
    if custom_path:
        search_paths.append(Path(custom_path).expanduser())
    
    search_paths.extend(DEFAULT_PATHS)

    parser = configparser.ConfigParser()
    
    for path in search_paths:
        if path.exists():
            try:
                parser.read(path)
                if "proxysql" in parser:
                    cfg = parser["proxysql"]
                    
                    # Parse excluded_users as a list
                    excluded_users_str = cfg.get("excluded_users", "")
                    excluded_users = [
                        u.strip() for u in excluded_users_str.split(",")
                        if u.strip()
                    ] if excluded_users_str else DEFAULT_CONFIG["excluded_users"].copy()
                    
                    return {
                        "host": cfg.get("host", DEFAULT_CONFIG["host"]),
                        "port": cfg.getint("port", DEFAULT_CONFIG["port"]),
                        "user": cfg.get("user", DEFAULT_CONFIG["user"]),
                        "password": cfg.get("password", DEFAULT_CONFIG["password"]),
                        "default_hostgroup": cfg.getint(
                            "default_hostgroup",
                            DEFAULT_CONFIG["default_hostgroup"]
                        ),
                        "excluded_users": excluded_users,
                        "_source": str(path)
                    }
            except (configparser.Error, ValueError) as e:
                # Log warning but continue to next path
                print(f"[proxysqlAdmin] Warning: Failed to parse {path}: {e}")
                continue
    
    raise FileNotFoundError(
        f"No ProxySQL config found. Searched in: {[str(p) for p in search_paths]}.\n"
        f"Create a config file or set the {ENV_CONFIG_VAR} environment variable."
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
        ValueError: If the file is missing the [proxysql] section.
        configparser.Error: If the file cannot be parsed.

    Example:
        >>> cfg = load_proxysql_config_from("/etc/myapp/proxysql.conf")
        >>> print(f"Host: {cfg['host']}")
    """
    path = Path(path).expanduser()
    
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    
    parser = configparser.ConfigParser()
    
    try:
        parser.read(path)
    except configparser.Error as e:
        raise ValueError(f"Failed to parse configuration file {path}: {e}") from e
    
    if "proxysql" not in parser:
        raise ValueError(
            f"Missing [proxysql] section in configuration file: {path}\n"
            f"Example:\n[proxysql]\nhost = 127.0.0.1\nport = 6032"
        )
    
    cfg = parser["proxysql"]
    
    # Parse excluded_users as a list
    excluded_users_str = cfg.get("excluded_users", "")
    excluded_users = [
        u.strip() for u in excluded_users_str.split(",")
        if u.strip()
    ] if excluded_users_str else DEFAULT_CONFIG["excluded_users"].copy()
    
    return {
        "host": cfg.get("host", DEFAULT_CONFIG["host"]),
        "port": cfg.getint("port", DEFAULT_CONFIG["port"]),
        "user": cfg.get("user", DEFAULT_CONFIG["user"]),
        "password": cfg.get("password", DEFAULT_CONFIG["password"]),
        "default_hostgroup": cfg.getint(
            "default_hostgroup",
            DEFAULT_CONFIG["default_hostgroup"]
        ),
        "excluded_users": excluded_users,
        "_source": str(path)
    }


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

    Searches the same locations as load_proxysql_config() but never raises;
    it simply reports whether a usable config file is present.

    Returns:
        The Path of the first existing config file, or None.
    """
    for path in get_config_search_paths():
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

    parser = configparser.ConfigParser()
    parser["proxysql"] = {
        "host": str(values.get("host", DEFAULT_CONFIG["host"])),
        "port": str(values.get("port", DEFAULT_CONFIG["port"])),
        "user": str(values.get("user", DEFAULT_CONFIG["user"])),
        "password": str(values.get("password", DEFAULT_CONFIG["password"])),
        "default_hostgroup": str(
            values.get("default_hostgroup", DEFAULT_CONFIG["default_hostgroup"])
        ),
        "excluded_users": excluded,
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
