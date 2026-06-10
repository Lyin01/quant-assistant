#!/usr/bin/env python3
"""Scan liquid ETFs or A-shares for continuation-trend candidates."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from quant_assistant.market_scanner import DEFAULT_SCAN_LIMIT, MARKET_UNIVERSES, SCAN_MODES, scan_market


DEFAULT_COLUMNS = [
    "排名",
    "类型",
    "代码",
    "名称",
    "价格",
    "候选分",
    "连涨趋势分",
    "趋势等级",
    "买入建议",
    "持有/卖出建议",
    "观察建议",
    "风险提示",
    "5日涨幅%",
    "10日涨幅%",
    "20日涨幅%",
    "5日上涨天数",
    "10日上涨天数",
    "连续上涨天数",
    "MA20斜率%",
    "20日回撤%",
    "RSI",
    "量比",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="ETF / A股 连涨趋势扫描排行")
    parser.add_argument(
        "--universe",
        choices=sorted(MARKET_UNIVERSES),
        default="etf",
        help="扫描范围: etf=ETF, stock=A股, all=ETF+A股",
    )
    parser.add_argument("--top-n", type=int, default=DEFAULT_SCAN_LIMIT, help="按成交额扫描前 N 个标的")
    parser.add_argument("--workers", type=int, default=6, help="并发抓取数量")
    parser.add_argument("--limit", type=int, default=20, help="输出前 N 条排行")
    parser.add_argument("--mode", choices=sorted(SCAN_MODES), default="balanced", help="选股模式: strict=稳健, balanced=均衡, aggressive=进攻")
    parser.add_argument("--include-defensive", action="store_true", help="包含货币/债券类 ETF")
    parser.add_argument("--force-refresh", action="store_true", help="跳过本地缓存重新抓取")
    parser.add_argument("--csv", type=Path, help="可选：把完整结果导出为 CSV")
    args = parser.parse_args()

    frame, messages = scan_market(
        universe=args.universe,
        top_n=args.top_n,
        max_workers=args.workers,
        force_refresh=args.force_refresh,
        mode=args.mode,
        include_defensive=args.include_defensive,
    )
    if frame.empty:
        print("市场扫描没有返回数据。")
        for message in messages:
            print(f"- {message}")
        return 1

    columns = [column for column in DEFAULT_COLUMNS if column in frame.columns]
    output = frame[columns].head(args.limit).copy()
    print(output.to_string(index=False, float_format=lambda value: f"{value:.2f}"))

    print("\n数据源状态:")
    for message in messages:
        print(f"- {message}")

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.csv, index=False, encoding="utf-8-sig")
        print(f"\nCSV 已导出: {args.csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
