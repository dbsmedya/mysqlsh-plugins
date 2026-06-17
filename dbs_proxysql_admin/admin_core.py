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

"""Core helpers for the ProxySQL admin plugin.

Provides interactive-mode detection, user prompts, the session-scoped active
configuration pointer and the configuration creation wizard. The active
configuration is kept in a module global, so it is naturally scoped to a single
MySQL Shell session and resets when the shell restarts.
"""

import threading
from typing import Any, Dict, Optional, Tuple

import mysqlsh

from dbs_proxysql_admin.load_proxysql_config import (
    DEFAULT_CONFIG,
    DEFAULT_WRITE_PATH,
    find_existing_config,
    save_proxysql_config,
)

# Session-scoped active configuration path.
_active_config_path: Optional[str] = None


def set_active_config_path(path: Optional[str]) -> None:
    """Set the active configuration path for this session."""
    global _active_config_path
    _active_config_path = str(path) if path else None


def get_active_config_path() -> Optional[str]:
    """Return the active configuration path, or None if none is set."""
    return _active_config_path


def clear_active_config_path() -> None:
    """Clear the active configuration path."""
    global _active_config_path
    _active_config_path = None


def resolve_config_path(config_path: Optional[str] = None) -> Optional[str]:
    """Return the explicit path if given, else the active path, else None."""
    if config_path:
        return config_path
    return _active_config_path


def get_interactive_default() -> bool:
    """Return True when running interactively on the shell main thread."""
    try:
        if mysqlsh.globals.shell.options.useWizards:
            ct = threading.current_thread()
            if ct.__class__.__name__ == "_MainThread":
                return True
    except Exception:
        pass
    return False


def prompt(message: str, options: Optional[Dict[str, Any]] = None) -> str:
    """Prompt the user for input, always returning a string."""
    if options:
        answer = mysqlsh.globals.shell.prompt(message, options)
    else:
        answer = mysqlsh.globals.shell.prompt(message)
    return answer if answer is not None else ""


def mysql_session_connected() -> bool:
    """Return True when an open MySQL session is available."""
    try:
        session = mysqlsh.globals.session
        return bool(session and session.is_open())
    except Exception:
        return False


def _resolve_field(value, label, default, interactive, is_password=False):
    """Return a provided value, else prompt in interactive mode, else default."""
    if value is not None and value != "":
        return value
    if interactive:
        if is_password:
            answer = prompt(
                f"{label} (press Enter to keep default): ",
                {"type": "password"})
        else:
            answer = prompt(f"{label} [{default}]: ", {"defaultValue": str(default)})
        answer = (answer or "").strip()
        if answer:
            return answer
    return default


def run_config_wizard(config_path: Optional[str] = None,
                      provided: Optional[Dict[str, Any]] = None,
                      interactive: bool = True) -> Tuple[str, Dict[str, Any]]:
    """Gather configuration values and write them to an INI file.

    Missing values are prompted for in interactive mode; otherwise defaults are
    used. Returns a tuple of the written file path and the values written.
    """
    provided = provided or {}

    if not config_path:
        if interactive:
            default_path = str(DEFAULT_WRITE_PATH)
            answer = prompt(
                f"Path to save the ProxySQL config [{default_path}]: ",
                {"defaultValue": default_path})
            config_path = (answer or "").strip() or default_path
        else:
            config_path = str(DEFAULT_WRITE_PATH)

    host = _resolve_field(
        provided.get("host"), "ProxySQL admin host",
        DEFAULT_CONFIG["host"], interactive)
    port = int(_resolve_field(
        provided.get("port"), "ProxySQL admin port",
        DEFAULT_CONFIG["port"], interactive))
    user = _resolve_field(
        provided.get("user"), "ProxySQL admin user",
        DEFAULT_CONFIG["user"], interactive)
    password = _resolve_field(
        provided.get("password"), "ProxySQL admin password",
        DEFAULT_CONFIG["password"], interactive, is_password=True)
    default_hostgroup = int(_resolve_field(
        provided.get("default_hostgroup"), "Default hostgroup for new users",
        DEFAULT_CONFIG["default_hostgroup"], interactive))

    excluded = provided.get("excluded_users")
    if excluded is None:
        excluded = _resolve_field(
            None, "Excluded users (comma separated)",
            ", ".join(DEFAULT_CONFIG["excluded_users"]), interactive)
    if isinstance(excluded, str):
        excluded_list = [u.strip() for u in excluded.split(",") if u.strip()]
    else:
        excluded_list = list(excluded)

    values = {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "default_hostgroup": default_hostgroup,
        "excluded_users": excluded_list,
    }

    path = save_proxysql_config(config_path, values)
    return path, values


def ensure_config(config_path: Optional[str], interactive: bool) -> Optional[str]:
    """Resolve a usable config path, offering the wizard when none exists.

    Returns an explicit path, or None to mean the loader should use its default
    search. When no configuration is available the wizard is offered in
    interactive mode; otherwise a FileNotFoundError is raised.
    """
    path = resolve_config_path(config_path)
    if path:
        return path

    if find_existing_config() is not None:
        return None

    if interactive:
        answer = prompt(
            "No ProxySQL config found. Create one now? [Y/n]: ",
            {"defaultValue": "y"}).strip().lower()
        if answer in ("", "y", "yes"):
            new_path, _ = run_config_wizard(None, interactive=True)
            set_active_config_path(new_path)
            print(f"Created and activated ProxySQL config: {new_path}")
            return new_path

    raise FileNotFoundError(
        "No ProxySQL configuration found. Run createConfig() to create one, "
        "or pass config_path explicitly."
    )
