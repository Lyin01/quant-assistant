from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_json
from .data_provider import build_provider, collect_secids, quote_status
from .journal import append_recommendations
from .strategy import generate_recommendations


def main() -> int:
    parser = argparse.ArgumentParser(description="Local quant assistant")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--portfolio", default="portfolio.json")
    parser.add_argument("--no-live", action="store_true", help="Do not fetch live quotes; use last_daily_pct.")
    parser.add_argument("--save-log", action="store_true", help="Append recommendations to data/journal.csv.")
    args = parser.parse_args()

    root = Path(args.config).resolve().parent
    config = load_json(args.config)
    portfolio = load_json(args.portfolio)

    quotes = {}
    quote_messages: list[str] = []
    if not args.no_live:
        provider = build_provider(config)
        quotes, quote_messages = provider.get_quotes_with_status(collect_secids(config, portfolio))

    recommendations = generate_recommendations(config, portfolio, quotes)
    _print_report(config, portfolio, recommendations, quote_messages, live=bool(quotes))

    if args.save_log:
        append_recommendations(root / "data" / "journal.csv", recommendations)
        print(f"\n日志已写入: {root / 'data' / 'journal.csv'}")

    return 0


def _print_report(
    config: dict,
    portfolio: dict,
    recommendations: list[dict[str, str]],
    quote_messages: list[str],
    live: bool,
) -> None:
    fund = portfolio["accounts"]["fund"]
    stock = portfolio["accounts"]["stock"]
    quote_mode = "实时行情" if live else "本地快照"

    print("Quant Assistant")
    print(f"数据时间: {portfolio.get('as_of', '-')}")
    print(f"行情模式: {quote_mode}")
    print(quote_status(config))
    print(f"基金资产: {fund['total_assets']:,.2f}  今日盈亏: {fund['today_pnl']:,.2f}")
    print(f"股票资产: {stock['total_assets']:,.2f}  可用资金: {stock['available_cash']:,.2f}")
    if quote_messages:
        print("\n行情源状态:")
        for message in quote_messages:
            print(f"- {message}")
    print("\n今日建议:")

    for rec in recommendations:
        print(f"- {rec['action']:9} {rec['instrument']} {rec['amount']}")
        print(f"  原因: {rec['reason']}")


if __name__ == "__main__":
    raise SystemExit(main())
