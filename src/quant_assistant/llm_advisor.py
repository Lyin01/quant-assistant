from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-pro"


@dataclass(frozen=True)
class DeepSeekSettings:
    api_key: str = ""
    base_url: str = DEFAULT_DEEPSEEK_BASE_URL
    model: str = DEFAULT_DEEPSEEK_MODEL

    @property
    def configured(self) -> bool:
        return bool(self.api_key.strip())


def load_deepseek_settings(project_root: str | Path) -> DeepSeekSettings:
    # Try python-dotenv first for robust .env loading
    _try_load_dotenv(Path(project_root) / ".env")
    env_values = _load_env_file(Path(project_root) / ".env")
    secret_values = _load_streamlit_secrets()
    api_key = (
        os.getenv("DEEPSEEK_API_KEY")
        or secret_values.get("DEEPSEEK_API_KEY", "")
        or env_values.get("DEEPSEEK_API_KEY", "")
    )
    base_url = (
        os.getenv("DEEPSEEK_BASE_URL")
        or secret_values.get("DEEPSEEK_BASE_URL", "")
        or env_values.get("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL)
    )
    model = (
        os.getenv("DEEPSEEK_MODEL")
        or secret_values.get("DEEPSEEK_MODEL", "")
        or env_values.get("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL)
    )
    return DeepSeekSettings(
        api_key=api_key.strip(),
        base_url=base_url.strip().rstrip("/") or DEFAULT_DEEPSEEK_BASE_URL,
        model=model.strip() or DEFAULT_DEEPSEEK_MODEL,
    )


def build_llm_context(
    config: dict[str, Any],
    portfolio: dict[str, Any],
    recommendations: list[dict[str, str]],
    quotes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    position_strategy_tag = _load_position_strategy_tag()
    fund = portfolio["accounts"]["fund"]
    stock = portfolio["accounts"]["stock"]

    fund_positions = [position for position in fund.get("positions", []) if isinstance(position, dict)]
    stock_positions = [position for position in stock.get("positions", []) if isinstance(position, dict)]
    total_assets = _number(fund.get("total_assets")) + _number(stock.get("total_assets"))
    stock_mv = _number(stock.get("market_value"))
    stock_cash = _number(stock.get("available_cash"))

    stock_by_mv = sorted(stock_positions, key=lambda p: _number(p.get("market_value")), reverse=True)
    top_stock = stock_by_mv[0] if stock_by_mv else None
    top_market_value = _number(top_stock.get("market_value")) if top_stock else 0.0
    concentration_pct = (top_market_value / stock_mv * 100) if top_stock and stock_mv else 0

    uncovered_positions = []
    for position in stock_positions:
        tag = _safe_position_strategy_tag(position_strategy_tag, config, position, "stock")
        if tag != "imported":
            continue
        uncovered_positions.append({
            "account": "stock",
            "name": str(position.get("name", "")),
            "tag": tag or position.get("tag", "unknown"),
            "market_value": _number(position.get("market_value")),
            "holding_pnl_pct": _number(position.get("holding_pnl_pct")),
            "shares": _whole_number(position.get("shares")),
            "price": _number(position.get("price")),
            "cost": _number(position.get("cost")),
        })

    rec_groups = {
        "sell": [rec for rec in recommendations if rec.get("action") == "SELL"],
        "buy": [rec for rec in recommendations if rec.get("action") in {"BUY", "LIMIT_BUY"}],
        "hold": [rec for rec in recommendations if rec.get("action") not in {"SELL", "BUY", "LIMIT_BUY"}],
    }

    coverage_issues = [
        {
            "账户": "股票",
            "标的": position["name"],
            "问题": "无策略覆盖",
            "建议": f"当前 tag={position['tag']}，市值 {position['market_value']:.2f}，请补充规则或人工盯盘。",
        }
        for position in uncovered_positions
    ]

    return {
        "total_assets": round(total_assets, 2),
        "fund": {
            "total_assets": round(_number(fund.get("total_assets")), 2),
            "today_pnl": round(_number(fund.get("today_pnl")), 2),
            "position_count": len(fund_positions),
        },
        "stock": {
            "total_assets": round(_number(stock.get("total_assets")), 2),
            "market_value": round(stock_mv, 2),
            "available_cash": round(stock_cash, 2),
            "today_pnl": round(_number(stock.get("today_pnl")), 2),
            "holding_pnl": round(_number(stock.get("holding_pnl")), 2),
            "position_count": len(stock_positions),
        },
        "concentration": {
            "top_name": top_stock.get("name") if top_stock else None,
            "top_market_value": top_market_value,
            "concentration_pct": round(concentration_pct, 2),
        },
        "cash_stress": stock_cash < 100,
        "uncovered_positions": uncovered_positions,
        "coverage_issues": coverage_issues,
        "recommendations": rec_groups,
        "quotes": quotes or {},
    }


def generate_llm_prompt(ctx: dict[str, Any]) -> str:
    return build_llm_prompt(
        portfolio={
            "accounts": {
                "fund": ctx.get("fund", {}),
                "stock": {
                    "total_assets": ctx.get("stock", {}).get("total_assets", 0),
                    "today_pnl": ctx.get("stock", {}).get("today_pnl", 0),
                    "available_cash": ctx.get("stock", {}).get("available_cash", 0),
                },
            }
        },
        actionable_recommendations=ctx.get("recommendations", {}).get("sell", []) + ctx.get("recommendations", {}).get("buy", []),
        watchlist_recommendations=ctx.get("recommendations", {}).get("hold", []),
        coverage_issues=ctx.get("coverage_issues", []),
        data_source="实时行情" if ctx.get("quotes") else "持仓快照",
        quote_freshness={"status": "已构建上下文", "detail": "由规则引擎和持仓数据生成"},
    )


def build_llm_prompt(
    portfolio: dict[str, Any],
    actionable_recommendations: list[dict[str, str]],
    watchlist_recommendations: list[dict[str, str]],
    coverage_issues: list[dict[str, str]],
    data_source: str,
    quote_freshness: dict[str, Any],
) -> str:
    fund = portfolio.get("accounts", {}).get("fund", {})
    stock = portfolio.get("accounts", {}).get("stock", {})
    header_lines = [
        "你是我的A股/基金复盘助手。请基于以下规则引擎结果，给我一份更像交易复盘笔记的中文建议。",
        "要求：",
        "1. 不要替我自动下单，不要假设未来一定上涨或下跌。",
        "2. 先给结论摘要，再按“今日动作 / 继续持有 / 人工关注风险”分组。",
        "3. 明确区分规则引擎已触发动作和你补充的人工判断。",
        "4. 如果存在无策略覆盖持仓，单独列出并说明应观察什么。",
        "5. 输出尽量简洁，适合直接阅读，不要复述全部原始数据。",
        "",
        "=== 账户概况 ===",
        f"- 基金资产：{_number(fund.get('total_assets')):.2f}",
        f"- 基金今日盈亏：{_number(fund.get('today_pnl')):.2f}",
        f"- 股票资产：{_number(stock.get('total_assets')):.2f}",
        f"- 股票今日盈亏：{_number(stock.get('today_pnl')):.2f}",
        f"- 股票可用现金：{_number(stock.get('available_cash')):.2f}",
        f"- 数据来源：{data_source}",
        f"- 行情状态：{quote_freshness.get('status', '未知')}，{quote_freshness.get('detail', '无详情')}",
        "",
        "=== 规则引擎动作建议 ===",
    ]

    actionable_lines = _format_recommendations(actionable_recommendations)
    if not actionable_lines:
        actionable_lines = ["- 当前没有触发买入、卖出或限价买入动作。"]

    watchlist_lines = ["", "=== 规则引擎 HOLD 列表 ==="]
    hold_lines = _format_recommendations(watchlist_recommendations)
    if not hold_lines:
        hold_lines = ["- 当前没有 HOLD 观察项。"]

    coverage_lines = ["", "=== 无策略覆盖/配置提示 ==="]
    if coverage_issues:
        coverage_lines.extend(
            f"- {issue.get('账户', '未知账户')} / {issue.get('标的', '未知标的')}：{issue.get('问题', '未知问题')}。{issue.get('建议', '')}"
            for issue in coverage_issues
        )
    else:
        coverage_lines.append("- 当前未发现明显的策略覆盖缺口。")

    return "\n".join(header_lines + actionable_lines + watchlist_lines + hold_lines + coverage_lines).strip()


def build_local_rule_advice(
    portfolio: dict[str, Any],
    actionable_recommendations: list[dict[str, str]],
    watchlist_recommendations: list[dict[str, str]],
    coverage_issues: list[dict[str, str]],
    data_source: str,
    quote_freshness: dict[str, Any],
) -> str:
    fund = portfolio.get("accounts", {}).get("fund", {})
    stock = portfolio.get("accounts", {}).get("stock", {})
    action_count = len(actionable_recommendations)
    watch_count = len(watchlist_recommendations)
    issue_count = len(coverage_issues)

    lines = [
        "### 本地规则摘要（非 LLM）",
        f"- 数据来源：{data_source}；行情状态：{quote_freshness.get('status', '未知')}。",
        f"- 基金资产：{_number(fund.get('total_assets')):.2f}；股票资产：{_number(stock.get('total_assets')):.2f}；股票可用现金：{_number(stock.get('available_cash')):.2f}。",
        f"- 今日动作 {action_count} 条，观察项 {watch_count} 条，策略配置提示 {issue_count} 条。",
    ]

    if not quote_freshness.get("reliable", True):
        detail = str(quote_freshness.get("detail", "")).strip()
        lines.append(f"- 行情可靠性不足：{detail or '建议只参考快照和历史复盘。'}")

    lines.extend(["", "#### 今日动作"])
    if actionable_recommendations:
        lines.extend(_format_recommendations(actionable_recommendations[:8]))
        if len(actionable_recommendations) > 8:
            lines.append(f"- 其余 {len(actionable_recommendations) - 8} 条动作请查看上方表格。")
    else:
        lines.append("- 当前没有触发买入、卖出或限价买入动作。")

    lines.extend(["", "#### 重点观察"])
    if watchlist_recommendations:
        lines.extend(_format_recommendations(watchlist_recommendations[:8]))
        if len(watchlist_recommendations) > 8:
            lines.append(f"- 其余 {len(watchlist_recommendations) - 8} 条观察项请查看上方 HOLD 列表。")
    else:
        lines.append("- 当前没有 HOLD 观察项。")

    lines.extend(["", "#### 人工复核"])
    if coverage_issues:
        for issue in coverage_issues[:8]:
            lines.append(
                f"- {issue.get('账户', issue.get('璐︽埛', '未知账户'))} / "
                f"{issue.get('标的', issue.get('鏍囩殑', '未知标的'))}："
                f"{issue.get('问题', issue.get('闂', '待复核'))}。"
                f"{issue.get('建议', issue.get('寤鸿', ''))}"
            )
        if len(coverage_issues) > 8:
            lines.append(f"- 其余 {len(coverage_issues) - 8} 条配置提示请查看策略覆盖检查。")
    else:
        lines.append("- 当前没有明显策略覆盖缺口。")

    lines.append("")
    lines.append("以上为规则引擎整理结果，不调用外部模型，不构成收益预测或自动下单。")
    return "\n".join(lines).strip()


def request_deepseek_advice(settings: DeepSeekSettings, prompt: str, timeout_seconds: int = 25) -> str:
    if not settings.configured:
        raise ValueError("DeepSeek API Key 未配置。")

    payload = {
        "model": settings.model,
        "messages": [
            {
                "role": "system",
                "content": "你是谨慎的中文量化复盘助手。只做复盘、风险提示和执行建议，不做收益承诺。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
    }
    request = Request(
        url=f"{settings.base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.api_key}",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek API 返回 HTTP {exc.code}：{detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"DeepSeek API 连接失败：{exc.reason}") from exc

    try:
        data = json.loads(raw)
        return str(data["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"DeepSeek API 返回格式无法解析：{raw[:500]}") from exc


def generate_advice(ctx: dict[str, Any]) -> dict[str, Any]:
    prompt = generate_llm_prompt(ctx)
    project_root = Path(__file__).resolve().parent.parent.parent
    settings = load_deepseek_settings(project_root)
    if settings.configured:
        try:
            text = request_deepseek_advice(settings, prompt)
            return {"mode": "api", "text": text, "usage": {}}
        except Exception as exc:
            return {"mode": "api_error", "text": f"API 调用失败: {exc}", "prompt": prompt}
    return {"mode": "prompt", "text": "(未配置 DeepSeek API Key，请复制下方 prompt 到 Kimi/DeepSeek 获取建议)", "prompt": prompt}


def parse_llm_response(text: str) -> dict[str, Any]:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    summary = ""
    actions: list[dict[str, str]] = []
    risks: list[str] = []
    current_section = "summary"

    for line in lines:
        lower = line.lower()
        if "摘要" in line or "总结" in line or "一句话" in line:
            current_section = "summary"
            continue
        if any(keyword in lower for keyword in ("卖出", "买入", "操作", "建议", "action")):
            current_section = "actions"
            continue
        if any(keyword in lower for keyword in ("风险", "注意", "提示", "warning")) or "⚠️" in line:
            current_section = "risks"
            continue

        if current_section == "summary":
            summary += line + " "
        elif current_section == "actions":
            actions.append({"text": line})
        else:
            risks.append(line)

    return {"summary": summary.strip(), "actions": actions, "risks": risks, "raw": text}


def _format_recommendations(recommendations: list[dict[str, str]]) -> list[str]:
    lines: list[str] = []
    for recommendation in recommendations:
        action = recommendation.get("action", "").strip() or "HOLD"
        instrument = recommendation.get("instrument", "").strip() or "未知标的"
        amount = recommendation.get("amount", "").strip()
        reason = recommendation.get("reason", "").strip()
        amount_text = f" {amount}" if amount else ""
        reason_text = f"：{reason}" if reason else ""
        lines.append(f"- {action} {instrument}{amount_text}{reason_text}")
    return lines


def _number(value: Any, default: float = 0.0) -> float:
    if value is None or isinstance(value, bool):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _whole_number(value: Any, default: int = 0) -> int:
    return int(_number(value, float(default)))


def _safe_position_strategy_tag(resolver: Any, config: dict[str, Any], position: dict[str, Any], account_key: str) -> str:
    try:
        return resolver(config, position, account_key)
    except (TypeError, ValueError):
        return str(position.get("tag", "unknown") or "unknown")


def _try_load_dotenv(env_path: Path) -> None:
    """Attempt to load .env using python-dotenv if available."""
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=str(env_path), override=False)
    except ImportError:
        pass
    except Exception:
        pass


def diagnose_config(project_root: str | Path) -> dict[str, Any]:
    """Return diagnostic info about DeepSeek config sources for debugging."""
    root = Path(project_root)
    env_path = root / ".env"
    result: dict[str, Any] = {
        "project_root": str(root),
        "env_file_exists": env_path.exists(),
        "env_file_path": str(env_path),
        "dotenv_available": False,
        "sources": {},
    }
    try:
        import dotenv  # noqa: F401
        result["dotenv_available"] = True
    except ImportError:
        pass

    def _mask(key: str) -> str:
        if not key or len(key) < 8:
            return "***"
        return f"{key[:6]}...{key[-4:]}"

    # Check env var
    env_key = os.getenv("DEEPSEEK_API_KEY", "")
    result["sources"]["env_var"] = f"已设置 ({_mask(env_key)})" if env_key else "未设置"

    # Check Streamlit secrets
    secret_values, secret_sources = _load_streamlit_secrets_with_sources()
    s_key = secret_values.get("DEEPSEEK_API_KEY", "")
    if s_key:
        source_path = secret_sources.get("DEEPSEEK_API_KEY", "未知位置")
        result["sources"]["streamlit_secrets"] = f"已配置 ({_mask(s_key)})，来源: {source_path}"
    else:
        result["sources"]["streamlit_secrets"] = "未配置"

    # Check .env file
    env_values = _load_env_file(env_path)
    f_key = env_values.get("DEEPSEEK_API_KEY", "")
    result["sources"]["env_file"] = f"已配置 ({_mask(f_key)})" if f_key else "未配置或不存在"

    return result


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _load_streamlit_secrets() -> dict[str, str]:
    return _load_streamlit_secrets_with_sources()[0]


def _load_streamlit_secrets_with_sources() -> tuple[dict[str, str], dict[str, str]]:
    try:
        import streamlit as st
        try:
            from streamlit.errors import StreamlitSecretNotFoundError
        except Exception:  # pragma: no cover - compatibility fallback
            StreamlitSecretNotFoundError = Exception

        values: dict[str, str] = {}
        sources: dict[str, str] = {}

        top_level_aliases = {
            "DEEPSEEK_API_KEY": ("DEEPSEEK_API_KEY", "deepseek_api_key"),
            "DEEPSEEK_BASE_URL": ("DEEPSEEK_BASE_URL", "deepseek_base_url"),
            "DEEPSEEK_MODEL": ("DEEPSEEK_MODEL", "deepseek_model"),
        }

        def _remember(normalized_key: str, raw: Any, source_path: str) -> None:
            if values.get(normalized_key):
                return
            if raw is None:
                return
            text = str(raw).strip()
            if not text:
                return
            values[normalized_key] = text
            sources[normalized_key] = source_path

        def _walk_mapping(node: Any, prefix: str = "") -> None:
            if not hasattr(node, "items"):
                return

            current_path = prefix or "root"

            for normalized_key, aliases in top_level_aliases.items():
                for alias in aliases:
                    if hasattr(node, "get"):
                        _remember(normalized_key, node.get(alias, ""), f"{current_path}.{alias}")
                    if values.get(normalized_key):
                        break

            if current_path.split(".")[-1].lower() == "deepseek" and hasattr(node, "get"):
                _remember("DEEPSEEK_API_KEY", node.get("api_key", ""), f"{current_path}.api_key")
                _remember("DEEPSEEK_BASE_URL", node.get("base_url", ""), f"{current_path}.base_url")
                _remember("DEEPSEEK_MODEL", node.get("model", ""), f"{current_path}.model")

            for child_key, child_value in node.items():
                if hasattr(child_value, "items"):
                    child_path = f"{current_path}.{child_key}" if prefix else str(child_key)
                    _walk_mapping(child_value, child_path)

        _walk_mapping(st.secrets)
        return values, sources
    except StreamlitSecretNotFoundError:
        return {}, {}
    except Exception:
        return {}, {}


def _load_position_strategy_tag():
    try:
        from .strategy import position_strategy_tag
        return position_strategy_tag
    except Exception:
        def _fallback(config: dict[str, Any], position: dict[str, Any], account_key: str) -> str:
            return str(position.get("tag", "")).strip()
        return _fallback
