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

import os
import shutil
import threading
from typing import Any, Dict, Optional, Tuple

import mysqlsh

from dbs_proxysql_admin.load_proxysql_config import (
    DEFAULT_CONFIG,
    DEFAULT_WRITE_PATH,
    ENV_CONFIG_VAR,
    ConfigValidationError,
    find_existing_config,
    load_proxysql_config_from,
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

    def _as_int(value, label):
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ValueError(f"{label} must be an integer, got '{value}'")

    host = _resolve_field(
        provided.get("host"), "ProxySQL admin host",
        DEFAULT_CONFIG["host"], interactive)
    port = _as_int(_resolve_field(
        provided.get("port"), "ProxySQL admin port",
        DEFAULT_CONFIG["port"], interactive), "port")
    user = _resolve_field(
        provided.get("user"), "ProxySQL admin user",
        DEFAULT_CONFIG["user"], interactive)
    password = _resolve_field(
        provided.get("password"), "ProxySQL admin password",
        DEFAULT_CONFIG["password"], interactive, is_password=True)
    default_hostgroup = _as_int(_resolve_field(
        provided.get("default_hostgroup"), "Default hostgroup for new users",
        DEFAULT_CONFIG["default_hostgroup"], interactive), "default_hostgroup")
    required_host = _resolve_field(
        provided.get("required_host"),
        "MySQL account host to sync, e.g. % or 10.%",
        DEFAULT_CONFIG["required_host"], interactive)

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
        "required_host": required_host,
    }

    path = save_proxysql_config(config_path, values)
    return path, values


def _offer_config_wizard(path: str, error_text: str,
                         backup: bool) -> Optional[str]:
    """Show the config error and offer to (re)create the file at ``path``.

    Returns the written path when the user accepts, or None when declined.
    With ``backup`` the existing (broken) file is copied to <path>.bak first
    so hand-entered credentials are never lost.
    """
    print(error_text)
    verb = "Recreate" if backup else "Create"
    answer = prompt(
        f"{verb} this configuration file with the wizard now? [y/N]: ",
        {"defaultValue": "n"}).strip().lower()
    if answer not in ("y", "yes"):
        return None
    if backup:
        backup_path = f"{path}.bak"
        try:
            shutil.copy2(path, backup_path)
            print(f"Backed up the previous file to: {backup_path}")
        except OSError:
            pass
    new_path, _ = run_config_wizard(path, interactive=True)
    print(f"{verb}d ProxySQL config: {new_path}")
    return new_path


def ensure_config(config_path: Optional[str], interactive: bool) -> Optional[str]:
    """Resolve and validate a usable config path, offering the wizard on failure.

    The resolved configuration (explicit path, active path, or the first file
    found by the default search) is validated strictly so that a broken file
    fails fast. In interactive mode a broken or missing file triggers an offer
    to (re)create it with the wizard — including when PROXYSQL_SYNC_CONFIG
    points to a non-existent file; when no configuration exists at all the
    creation wizard is offered. Non-interactively the validation error (or a
    FileNotFoundError) propagates to the caller.
    """
    path = resolve_config_path(config_path)
    if not path:
        try:
            existing = find_existing_config()
        except FileNotFoundError as exc:
            env_path = os.getenv(ENV_CONFIG_VAR)
            if interactive and env_path:
                created = _offer_config_wizard(env_path, str(exc), backup=False)
                if created:
                    return created
            raise
        if existing is not None:
            path = str(existing)

    if path:
        try:
            load_proxysql_config_from(path)
        except ConfigValidationError as exc:
            if interactive:
                created = _offer_config_wizard(path, str(exc), backup=True)
                if created:
                    return created
            raise
        except FileNotFoundError as exc:
            if interactive:
                created = _offer_config_wizard(path, str(exc), backup=False)
                if created:
                    return created
            raise
        return path

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
