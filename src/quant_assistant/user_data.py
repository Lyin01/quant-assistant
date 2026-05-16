from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


ROOT_DATA = Path("data")
USERS_DIR = ROOT_DATA / "users"

DEFAULT_PORTFOLIO: dict[str, Any] = {
    "as_of": "",
    "accounts": {
        "stock": {
            "total_assets": 0.0,
            "today_pnl": 0.0,
            "available_cash": 0.0,
            "positions": [],
        },
        "fund": {
            "total_assets": 0.0,
            "today_pnl": 0.0,
            "positions": [],
        },
    },
}


def _user_id(user: dict[str, Any]) -> str:
    import re
    provider = user.get("provider", "unknown")
    uid = user.get("id") or user.get("email", "anonymous")
    # 防止路径穿越：只保留字母数字和下划线
    safe_uid = re.sub(r"[^a-zA-Z0-9_@.+-]", "_", str(uid))
    return f"{provider}_{safe_uid}"


def _user_dir(user: dict[str, Any]) -> Path:
    uid = _user_id(user)
    return USERS_DIR / uid


def _ensure_user_dir(user: dict[str, Any]) -> Path:
    directory = _user_dir(user)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _default_config_path() -> Path:
    return Path("config.json")


def get_or_create_portfolio(user: dict[str, Any]) -> dict[str, Any]:
    directory = _ensure_user_dir(user)
    path = directory / "portfolio.json"
    if path.exists():
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    # First login: seed with default
    data = dict(DEFAULT_PORTFOLIO)
    data["as_of"] = "首次登录，请导入持仓"
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    return data


def save_portfolio(user: dict[str, Any], data: dict[str, Any]) -> None:
    directory = _ensure_user_dir(user)
    path = directory / "portfolio.json"
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def load_config(user: dict[str, Any]) -> dict[str, Any]:
    directory = _user_dir(user)
    user_config = directory / "config.json"
    if user_config.exists():
        with user_config.open("r", encoding="utf-8") as file:
            return json.load(file)
    # Fallback to global config.json
    global_config = _default_config_path()
    if global_config.exists():
        with global_config.open("r", encoding="utf-8") as file:
            return json.load(file)
    return {}


def user_history_file(user: dict[str, Any]) -> Path:
    return _ensure_user_dir(user) / "portfolio_history.jsonl"


def list_users() -> list[dict[str, Any]]:
    if not USERS_DIR.exists():
        return []
    users = []
    for entry in USERS_DIR.iterdir():
        if entry.is_dir():
            parts = entry.name.split("_", 1)
            if len(parts) == 2:
                users.append({"provider": parts[0], "id": parts[1], "dir": str(entry)})
    return users


def delete_user_data(user: dict[str, Any]) -> None:
    directory = _user_dir(user)
    if directory.exists():
        shutil.rmtree(directory)
