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


def find_default_file(name: str) -> Path:
    candidate = Path(name)
    if candidate.exists():
        return candidate
    fallback = Path("Quant assistant") / name
    if fallback.exists():
        return fallback
    return candidate


def _default_config_path() -> Path:
    return find_default_file("config.json")


def _clean_portfolio(data: dict[str, Any]) -> dict[str, Any]:
    """Remove corrupted positions and fix common data issues."""
    for account_key in ("fund", "stock"):
        account = data.get("accounts", {}).get(account_key, {})
        positions = account.get("positions", [])
        cleaned = []
        for pos in positions:
            name = str(pos.get("name", "")).strip()
            if not name:
                continue
            # Remove strategy tags accidentally appended to names
            for suffix in ("·wide_index", "wide_index", "·tactical_ai", "tactical_ai",
                           "·power_grid", "power_grid", "·military", "military",
                           "·semiconductor", "semiconductor", "·robot", "robot",
                           "·overseas", "overseas", "·healthcare", "healthcare",
                           "·defensive", "defensive", "·core_ai_dca", "core_ai_dca",
                           "·imported", "imported"):
                if name.endswith(suffix):
                    name = name[: -len(suffix)].rstrip("· ").strip()
                    break
            pos["name"] = name
            # Fix negative or zero market_value for fund positions
            mv = pos.get("market_value")
            if account_key == "fund" and mv is not None:
                try:
                    if float(mv) <= 0:
                        pos["market_value"] = 0
                except (TypeError, ValueError):
                    pass
            cleaned.append(pos)
        if cleaned:
            data["accounts"][account_key]["positions"] = cleaned
    return data


def _seed_portfolio_from_global() -> dict[str, Any]:
    """Try to load the root portfolio.json as seed for new users."""
    global_path = find_default_file("portfolio.json")
    if global_path.exists():
        with global_path.open("r", encoding="utf-8") as file:
            return json.load(file)
    return dict(DEFAULT_PORTFOLIO)


def _seed_history_if_empty(user: dict[str, Any], portfolio_data: dict[str, Any]) -> None:
    """Write an initial history record so the return curve has a starting point."""
    from quant_assistant.history import record_change, read_history

    history_file = user_history_file(user)
    existing = read_history(history_file, limit=1)
    if existing:
        return

    total_assets = 0.0
    for account in portfolio_data.get("accounts", {}).values():
        total_assets += float(account.get("total_assets", 0) or 0)

    if total_assets > 0:
        record_change(
            history_file,
            change_type="initial",
            account="all",
            delta={"added": [], "updated": [], "removed": []},
            summary={"total_assets": total_assets},
        )


def get_or_create_portfolio(user: dict[str, Any]) -> dict[str, Any]:
    directory = _ensure_user_dir(user)
    path = directory / "portfolio.json"
    if path.exists():
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        data = _clean_portfolio(data)
        _seed_history_if_empty(user, data)
        return data
    # First login: seed from global portfolio.json if available
    data = _seed_portfolio_from_global()
    data["as_of"] = data.get("as_of", "") or "首次登录，请导入持仓"
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    _seed_history_if_empty(user, data)
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
