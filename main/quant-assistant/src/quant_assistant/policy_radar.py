from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

import pandas as pd

from .disk_cache import load_generic_cache, save_generic_cache


# Policy keywords to track
POLICY_KEYWORDS = [
    "半导体", "芯片", "集成电路",
    "机器人", "人形机器人", "智能制造",
    "人工智能", "AI", "大模型", "算力",
    "新能源", "光伏", "储能", "风电",
    "低空经济", "无人机", "eVTOL",
    "商业航天", "卫星", "火箭",
    "生物医药", "创新药", "医疗器械",
    "数据要素", "数字经济", "东数西算",
    "设备更新", "以旧换新",
    "生育", "养老", "银发经济",
    "房地产", "保障房", "城中村",
    "消费", "内需", "消费券",
    "出口", "外贸", "跨境电商",
    "化债", "专项债", "地方债",
    "降准", "降息", "LPR",
    "资本市场", "IPO", "退市", "减持",
]


def fetch_policy_news(limit: int = 50) -> tuple[pd.DataFrame, list[str]]:
    cache_key = f"policy_news_{limit}"
    cached = load_generic_cache(cache_key)
    if cached is not None:
        return pd.DataFrame(cached), ["Policy: cache hit"]

    messages: list[str] = []
    all_news: list[dict[str, str]] = []

    # Source 1: EastMoney 财经要闻
    try:
        eastmoney_news = _fetch_eastmoney_news(limit)
        all_news.extend(eastmoney_news)
        messages.append(f"EastMoney news: {len(eastmoney_news)} items")
    except Exception as exc:
        messages.append(f"EastMoney news: {exc}")

    if not all_news:
        return pd.DataFrame(), messages

    # Classify by keywords
    for item in all_news:
        title = item.get("title", "")
        matched = [kw for kw in POLICY_KEYWORDS if kw in title]
        item["tags"] = ", ".join(matched) if matched else ""
        item["is_policy"] = bool(matched)

    df = pd.DataFrame(all_news)
    # Sort: policy-related first, then by time
    df["_sort"] = df["is_policy"].astype(int) * 2 + (df["tags"] != "").astype(int)
    df = df.sort_values("_sort", ascending=False).drop(columns=["_sort"]).reset_index(drop=True)

    # Convert DataFrame to dict for JSON serialization
    save_generic_cache(cache_key, df.to_dict(orient="records"))
    return df, messages


def _fetch_eastmoney_news(limit: int) -> list[dict[str, str]]:
    # EastMoney 快讯 API（财经要闻，column=102）
    url = (
        "https://newsapi.eastmoney.com/kuaixun/v1/"
        f"getlist_102_ajaxResult_{limit}_1_.html"
    )
    request = urllib.request.Request(
        url,
        headers={
            "Referer": "https://www.eastmoney.com/",
            "User-Agent": "Mozilla/5.0 QuantAssistant/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        raw = response.read().decode("utf-8")

    # Response wrapped as: var ajaxResult={...}
    if "{" not in raw:
        return []
    json_start = raw.index("{")
    payload = json.loads(raw[json_start:])

    rows = payload.get("LivesList", [])
    results = []
    for row in rows:
        if isinstance(row, dict):
            url_w = str(row.get("url_w", row.get("url_unique", "")))
            # Derive source from the URL host
            source = "EastMoney"
            if "global.eastmoney.com" in url_w:
                source = "环球财经"
            elif "finance.eastmoney.com" in url_w:
                source = "东方财富"
            elif "forex.eastmoney.com" in url_w:
                source = "外汇"
            results.append({
                "title": str(row.get("title", "")),
                "time": str(row.get("showtime", row.get("ordertime", ""))),
                "source": source,
                "url": url_w,
            })
    return results


def summarize_policy_trends(df: pd.DataFrame, top_n: int = 10) -> list[dict[str, Any]]:
    """Extract trending policy themes from news."""
    if df.empty:
        return []

    policy_df = df[df["is_policy"] == True]
    if policy_df.empty:
        return []

    from collections import Counter
    tag_counter: Counter = Counter()
    for tags in policy_df["tags"]:
        for tag in str(tags).split(", "):
            if tag.strip():
                tag_counter[tag.strip()] += 1

    trends = []
    for tag, count in tag_counter.most_common(top_n):
        examples = policy_df[policy_df["tags"].str.contains(tag, na=False)]["title"].head(3).tolist()
        trends.append({
            "主题": tag,
            "提及次数": count,
            "最新标题": examples[0] if examples else "",
        })
    return trends
