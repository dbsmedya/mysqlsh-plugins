import os
import configparser
from pathlib import Path
from typing import Dict, Any, List

DEFAULT_PATHS: List[Path] = [
    Path.home() / ".proxysql_config.ini",
    Path("/etc/proxysql_sync.conf"),
    Path.cwd() / "proxysql_config.ini"
]

def load_proxysql_config() -> Dict[str, Any]:
    """Load ProxySQL credentials from environment or default paths."""
    custom_path: str | None = os.getenv("PROXYSQL_SYNC_CONFIG")
    search_paths: List[Path] = [Path(custom_path).expanduser()] if custom_path else []
    search_paths += DEFAULT_PATHS

    parser: configparser.ConfigParser = configparser.ConfigParser()
    for path in search_paths:
        if path.exists():
            parser.read(path)
            if "proxysql" in parser:
                cfg: configparser.SectionProxy = parser["proxysql"]
                
                # Parse excluded_users as a list
                excluded_users_str = cfg.get("excluded_users", "")
                excluded_users = [u.strip() for u in excluded_users_str.split(",")] if excluded_users_str else []
                
                return {
                    "host": cfg.get("host", "127.0.0.1"),
                    "port": cfg.getint("port", 6032),
                    "user": cfg.get("user", "admin"),
                    "password": cfg.get("password", "admin"),
                    "default_hostgroup": cfg.getint("default_hostgroup", 0),
                    "excluded_users": excluded_users,
                    "_source": str(path)
                }
    raise FileNotFoundError(f"No ProxySQL config found in {search_paths}")

def load_proxysql_config_from(path: Path) -> Dict[str, Any]:
    """Load ProxySQL credentials from a specific file path."""
    parser: configparser.ConfigParser = configparser.ConfigParser()
    path = Path(path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"No such config file: {path}")
    parser.read(path)
    if "proxysql" not in parser:
        raise ValueError(f"Missing [proxysql] section in {path}")
    cfg: configparser.SectionProxy = parser["proxysql"]
    
    # Parse excluded_users as a list
    excluded_users_str = cfg.get("excluded_users", "")
    excluded_users = [u.strip() for u in excluded_users_str.split(",")] if excluded_users_str else []
    
    return {
        "host": cfg.get("host", "127.0.0.1"),
        "port": cfg.getint("port", 6032),
        "user": cfg.get("user", "admin"),
        "password": cfg.get("password", "admin"),
        "default_hostgroup": cfg.getint("default_hostgroup", 0),
        "excluded_users": excluded_users,
        "_source": str(path)
    }
