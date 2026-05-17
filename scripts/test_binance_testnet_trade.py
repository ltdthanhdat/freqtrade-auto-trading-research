from __future__ import annotations

import argparse
import os
import sys

import ccxt


DEFAULT_SYMBOL = "BTC/USDT:USDT"
DEFAULT_QUOTE_AMOUNT = 60.0
DEFAULT_PRICE_OFFSET = 0.04


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test Binance futures testnet auth va duong create/cancel order."
    )
    parser.add_argument(
        "--symbol",
        default=DEFAULT_SYMBOL,
        help="Freqtrade/CCXT symbol futures. Mac dinh: BTC/USDT:USDT",
    )
    parser.add_argument(
        "--side",
        choices=["buy", "sell"],
        default="buy",
        help="Side cua lenh test.",
    )
    parser.add_argument(
        "--quote-amount",
        type=float,
        default=DEFAULT_QUOTE_AMOUNT,
        help="Notional USDT muc tieu cho lenh test.",
    )
    parser.add_argument(
        "--price-offset",
        type=float,
        default=DEFAULT_PRICE_OFFSET,
        help="Do lech gia limit so voi last price. 0.04 = 4%%.",
    )
    return parser.parse_args()


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    raise SystemExit(f"Missing required env var: {name}")


def build_exchange() -> ccxt.binance:
    exchange = ccxt.binance(
        {
            "apiKey": get_required_env("BINANCE_TESTNET_KEY"),
            "secret": get_required_env("BINANCE_TESTNET_SECRET"),
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",
                "adjustForTimeDifference": True,
            },
        }
    )
    exchange.enable_demo_trading(True)
    return exchange


def round_price(exchange: ccxt.binance, symbol: str, price: float) -> float:
    return float(exchange.price_to_precision(symbol, price))


def round_amount(exchange: ccxt.binance, symbol: str, amount: float) -> float:
    return float(exchange.amount_to_precision(symbol, amount))


def main() -> None:
    args = parse_args()
    exchange = build_exchange()

    try:
        market = exchange.load_markets()[args.symbol]
        ticker = exchange.fetch_ticker(args.symbol)
        balance = exchange.fetch_balance()

        last_price = float(ticker["last"])
        min_cost = float((market.get("limits", {}).get("cost") or {}).get("min") or 0)
        min_amount = float((market.get("limits", {}).get("amount") or {}).get("min") or 0)

        raw_price = last_price * (1 - args.price_offset if args.side == "buy" else 1 + args.price_offset)
        price = round_price(exchange, args.symbol, raw_price)

        target_quote = max(args.quote_amount, min_cost)
        raw_amount = max(target_quote / price, min_amount)
        amount = round_amount(exchange, args.symbol, raw_amount)

        order = exchange.create_order(
            symbol=args.symbol,
            type="limit",
            side=args.side,
            amount=amount,
            price=price,
        )

        canceled = exchange.cancel_order(order["id"], args.symbol)

        usdt_balance = balance.get("USDT", {})
        print("auth: ok")
        print(f"symbol: {args.symbol}")
        print(f"last_price: {last_price}")
        print(f"test_order: {args.side} {amount} @ {price}")
        print(f"balance_usdt_free: {usdt_balance.get('free')}")
        print(f"balance_usdt_total: {usdt_balance.get('total')}")
        print(f"created_order_id: {order['id']}")
        print(f"cancel_status: {canceled.get('status')}")
    except Exception as exc:
        print(f"auth_or_trade_test_failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
