import asyncio
from pathlib import Path

import yaml
from filelock import FileLock

from app.config import settings

LOCK_PATH = Path(settings.authelia_users_file).with_suffix(".lock")
_file_lock = FileLock(str(LOCK_PATH), timeout=10)


def _read_users_sync() -> dict:
    path = Path(settings.authelia_users_file)
    if not path.exists():
        return {"users": {}}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not data or "users" not in data:
        return {"users": {}}
    return data


def _write_users_sync(data: dict) -> None:
    path = Path(settings.authelia_users_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _username_exists_sync(username: str) -> bool:
    data = _read_users_sync()
    return username in data.get("users", {})


def _add_user_sync(
    username: str,
    display_name: str,
    email: str,
    password_hash: str,
    groups: list[str],
) -> None:
    with _file_lock:
        data = _read_users_sync()
        if username in data["users"]:
            raise ValueError(f"User '{username}' already exists in users database")

        data["users"][username] = {
            "disabled": False,
            "displayname": display_name,
            "password": password_hash,
            "email": email,
            "groups": groups,
        }
        _write_users_sync(data)


async def username_exists(username: str) -> bool:
    return await asyncio.to_thread(_username_exists_sync, username)


async def add_user(
    username: str,
    display_name: str,
    email: str,
    password_hash: str,
    groups: list[str] | None = None,
) -> None:
    if groups is None:
        groups = settings.groups_list
    await asyncio.to_thread(_add_user_sync, username, display_name, email, password_hash, groups)
