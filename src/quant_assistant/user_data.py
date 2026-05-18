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
        deduped: list[dict[str, Any]] = []
        seen_keys: list[tuple[str, int]] = []  # (dedup_key, index into deduped)

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
            # Filter garbage names
            if _is_garbage_name(name):
                continue
            # In stock account, filter out fund-like entries that don't belong
            if account_key == "stock" and _looks_like_fund_not_stock(name):
                continue
            pos["name"] = name
            # Fix negative or zero market_value for fund positions
            mv = pos.get("market_value")
            if account_key == "fund" and mv is not None:
                try:
                    if float(mv) <= 0:
                        pos["market_value"] = 0
                except (TypeError, ValueError):
                    pass
            # Deduplicate: keep the entry with richer data
            dkey = _dedup_key(name)
            matched_idx = None
            for key, idx in seen_keys:
                if _dedup_keys_match(key, dkey):
                    matched_idx = idx
                    break
            if matched_idx is not None:
                # Compare: keep the one with more fields filled
                existing = deduped[matched_idx]
                if _richness(pos) > _richness(existing):
                    deduped[matched_idx] = pos
            else:
                seen_keys.append((dkey, len(deduped)))
                deduped.append(pos)

        if deduped:
            data["accounts"][account_key]["positions"] = deduped
    return data


def _looks_like_fund_not_stock(name: str) -> bool:
    """Check if a name looks like a fund/index product rather than an individual stock.

    Stock names are typically 2-4 Chinese characters (公司名) or short ETF names.
    Fund names start with a fund house prefix (易方达, 天弘, etc.) or contain
    index keywords combined with a fund house prefix.
    """
    import re
    # Starts with a fund house prefix → almost certainly a fund
    for prefix in _FUND_HOUSES:
        if name.startswith(prefix):
            return True
    # Name matches an index pattern without any company context → likely fund holding
    if re.match(r"^(中证|沪深|科创|标普|纳斯达克|纳指|道琼斯)\S{0,6}$", name):
        return True
    return False


def _richness(pos: dict[str, Any]) -> int:
    """Count how many meaningful fields a position has."""
    score = 0
    for field in ("market_value", "shares", "price", "cost", "holding_pnl",
                  "holding_pnl_pct", "last_daily_pct", "market_proxy", "tag"):
        val = pos.get(field)
        if val is not None and val != "" and val != "imported":
            score += 1
    return score


def _dedup_keys_match(key_a: str, key_b: str) -> bool:
    """Check if two dedup keys refer to the same fund.

    Handles OCR truncation where one name may be a prefix of the other.
    e.g. "中证电网" matches "中证电网设备" (truncated by OCR).
    """
    if key_a == key_b:
        return True
    if not key_a or not key_b:
        return False
    # One is a prefix of the other (OCR truncation)
    shorter, longer = (key_a, key_b) if len(key_a) <= len(key_b) else (key_b, key_a)
    if len(longer) - len(shorter) <= 4 and longer.startswith(shorter):
        return True
    return False


_GARBAGE_NAMES = {
    "中", "RK", "rK", "Rk", "rk", "S", "s", "A", "a", "B", "b", "C", "c",
    "名称", "持仓", "市值", "现价", "成本", "可用", "自选",
}


_GENERIC_FUND_TYPES = {
    "混债", "纯债", "短债", "货基", "货币", "指数", "增强", "联接",
}


def _is_garbage_name(name: str) -> bool:
    """Check if a position name is obviously garbage/corrupted."""
    import re
    if len(name) < 2:
        return True
    if name in _GARBAGE_NAMES:
        return True
    # Pure ASCII single-letter tokens that aren't real fund names
    if len(name) <= 2 and name.isascii() and not any(c.isdigit() for c in name):
        return True
    # Names that are just numbers or punctuation
    if re.fullmatch(r"[\d\s.,;:!?%+\-*/=()]+", name):
        return True
    # Truncated OCR names ending with ellipsis or trailing punctuation
    if re.search(r"[……]{1,2}$", name) or re.search(r"\.{2,}$", name):
        return True
    # Single Chinese character names (except valid stock codes like "中兴")
    cjk_chars = re.findall(r"[一-鿿]", name)
    if len(cjk_chars) == 1 and len(name) <= 3:
        return True
    # Generic fund type keywords used alone (not a real position name)
    if name in _GENERIC_FUND_TYPES:
        return True
    # Fund house prefix + truncated = likely garbage from OCR
    for prefix in _FUND_HOUSES:
        if name.startswith(prefix) and len(name) < len(prefix) + 3:
            return True
    return False


_FUND_HOUSES = (
    "易方达", "天弘", "大成", "博时", "广发", "华宝", "华夏", "嘉实", "南方",
    "招商", "富国", "鹏华", "工银", "国泰", "汇添富", "景顺", "银华", "中欧",
    "兴全", "诺安", "交银", "建信", "农银", "长城", "万家", "平安", "海富通",
    "国联安", "华安", "中银", "信达澳银", "东吴", "长盛", "宝盈", "中海",
    "金鹰", "泰达宏利", "新华", "信诚", "益民", "银河", "中邮",
)


def _dedup_key(name: str) -> str:
    """Generate a normalized key for deduplication.

    Strips fund house prefixes and common suffixes to compare the core fund identity.
    e.g. "天弘中证电网设备" → "中证电网", "中证电网设备" → "中证电网"
    """
    import re
    core = name
    # Strip known fund house prefixes
    for prefix in _FUND_HOUSES:
        if core.startswith(prefix):
            core = core[len(prefix):]
            break
    # Strip common fund type suffixes
    for suffix in ("ETF联接", "ETF", "联接", "指数", "定投小仓", "定投大仓", "定投", "大仓", "小仓"):
        if core.endswith(suffix):
            core = core[:-len(suffix)]
            break
    # Remove remaining punctuation and whitespace
    core = re.sub(r"[\s·、，。\-]", "", core)
    return core.lower()


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
