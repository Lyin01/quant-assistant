from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_json
from .data_provider import EastMoneyProvider, collect_secids
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
    if not args.no_live:
        provider = EastMoneyProvider(timeout=config["market_provider"]["timeout_seconds"])
        quotes = provider.get_quotes(collect_secids(config, portfolio))

    recommendations = generate_recommendations(config, portfolio, quotes)
    _print_report(portfolio, recommendations, live=bool(quotes))

    if args.save_log:
        append_recommendations(root / "data" / "journal.csv", recommendations)
        print(f"\n日志已写入: {root / 'data' / 'journal.csv'}")

    return 0


def _print_report(portfolio: dict, recommendations: list[dict[str, str]], live: bool) -> None:
    fund = portfolio["accounts"]["fund"]
    stock = portfolio["accounts"]["stock"]
    quote_mode = "实时行情" if live else "本地快照"

    print("Quant Assistant")
    print(f"数据时间: {portfolio.get('as_of', '-')}")
    print(f"行情模式: {quote_mode}")
    print(f"基金资产: {fund['total_assets']:,.2f}  今日盈亏: {fund['today_pnl']:,.2f}")
    print(f"股票资产: {stock['total_assets']:,.2f}  可用资金: {stock['available_cash']:,.2f}")
    print("\n今日建议:")

    for rec in recommendations:
        print(f"- {rec['action']:9} {rec['instrument']} {rec['amount']}")
        print(f"  原因: {rec['reason']}")


if __name__ == "__main__":
    raise SystemExit(main())
