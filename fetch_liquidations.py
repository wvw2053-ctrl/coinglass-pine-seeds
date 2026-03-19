"""
Real Liquidation Level Calculator -> TradingView Pine Seeds
============================================================
Fetches REAL market data from Binance + Hyperliquid (free, no API key needed)
and calculates estimated liquidation levels based on:
  - Open Interest distribution
  - Long/Short ratios
  - Funding rates
  - Common leverage tiers (10x, 25x, 50x, 100x)

This replicates what Coinglass does internally for their Liquidation Map,
using only free, public API endpoints.

Outputs Pine Seeds CSV files for TradingView's request.seed() function.
"""

import json
import sys
import time
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Python 3 stdlib for HTTP (no external deps needed)
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


# ============================================================================
# HTTP HELPER
# ============================================================================

def http_get(url, timeout=15):
    """Simple GET request using stdlib."""
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "PineSeedsBot/1.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except (URLError, HTTPError) as e:
        print(f"  GET {url[:80]}... -> Error: {e}")
        return None


def http_post(url, payload, timeout=15):
    """Simple POST request using stdlib."""
    data = json.dumps(payload).encode()
    req = Request(url, data=data, headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "PineSeedsBot/1.0"
    })
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except (URLError, HTTPError) as e:
        print(f"  POST {url[:80]}... -> Error: {e}")
        return None


# ============================================================================
# BINANCE DATA (Free, no API key)
# ============================================================================

def fetch_binance_data():
    """Fetch BTC futures market data from Binance."""
    print("  [Binance] Fetching market data...")
    result = {}

    # 1. Current price
    ticker = http_get("https://fapi.binance.com/fapi/v1/ticker/price?symbol=BTCUSDT")
    if ticker:
        result["price"] = float(ticker["price"])
        print(f"    Price: ${result['price']:,.2f}")

    # 2. Open Interest
    oi = http_get("https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT")
    if oi:
        result["open_interest_btc"] = float(oi["openInterest"])
        print(f"    OI: {result['open_interest_btc']:,.2f} BTC")

    # 3. Top Trader Long/Short Position Ratio (last 24h, 1h intervals)
    tlsr = http_get("https://fapi.binance.com/futures/data/topLongShortPositionRatio?symbol=BTCUSDT&period=1h&limit=24")
    if tlsr and len(tlsr) > 0:
        latest = tlsr[-1]
        result["top_ls_ratio"] = float(latest["longShortRatio"])
        result["top_long_pct"] = float(latest["longAccount"])
        result["top_short_pct"] = float(latest["shortAccount"])
        print(f"    Top L/S Ratio: {result['top_ls_ratio']:.4f} (Long: {result['top_long_pct']:.1%})")

    # 4. Global Long/Short Account Ratio
    glsar = http_get("https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=BTCUSDT&period=1h&limit=24")
    if glsar and len(glsar) > 0:
        latest = glsar[-1]
        result["global_ls_ratio"] = float(latest["longShortRatio"])
        result["global_long_pct"] = float(latest["longAccount"])
        print(f"    Global L/S Ratio: {result['global_ls_ratio']:.4f} (Long: {result['global_long_pct']:.1%})")

    # 5. Funding Rate
    funding = http_get("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT")
    if funding:
        result["funding_rate"] = float(funding.get("lastFundingRate", 0))
        result["mark_price"] = float(funding.get("markPrice", 0))
        print(f"    Funding: {result['funding_rate']:.6f}")
        print(f"    Mark Price: ${result['mark_price']:,.2f}")

    # 6. 24h volume + price change
    stats = http_get("https://fapi.binance.com/fapi/v1/ticker/24hr?symbol=BTCUSDT")
    if stats:
        result["volume_24h_usd"] = float(stats.get("quoteVolume", 0))
        result["price_change_pct"] = float(stats.get("priceChangePercent", 0))
        print(f"    24h Volume: ${result['volume_24h_usd']:,.0f}")

    return result


# ============================================================================
# HYPERLIQUID DATA (Free, no API key)
# ============================================================================

def fetch_hyperliquid_data():
    """Fetch BTC data from Hyperliquid (completely free API)."""
    print("  [Hyperliquid] Fetching market data...")
    result = {}

    # 1. Meta + Asset Context (funding, OI, etc.)
    meta = http_post("https://api.hyperliquid.xyz/info", {"type": "metaAndAssetCtxs"})
    if meta and len(meta) >= 2:
        universe = meta[0].get("universe", [])
        contexts = meta[1]
        btc_idx = next((i for i, u in enumerate(universe) if u["name"] == "BTC"), None)
        if btc_idx is not None and btc_idx < len(contexts):
            ctx = contexts[btc_idx]
            result["hl_funding"] = float(ctx.get("funding", 0))
            result["hl_open_interest"] = float(ctx.get("openInterest", 0))
            result["hl_oracle_price"] = float(ctx.get("oraclePx", 0))
            result["hl_mark_price"] = float(ctx.get("markPx", 0))
            result["hl_max_leverage"] = universe[btc_idx].get("maxLeverage", 40)
            print(f"    OI: {result['hl_open_interest']:,.2f} BTC")
            print(f"    Oracle: ${result['hl_oracle_price']:,.2f}")
            print(f"    Funding: {result['hl_funding']:.6f}")
            print(f"    Max Leverage: {result['hl_max_leverage']}x")

    # 2. L2 Orderbook (top 20 levels - shows where liquidity clusters)
    book = http_post("https://api.hyperliquid.xyz/info", {"type": "l2Book", "coin": "BTC"})
    if book and "levels" in book:
        bids = book["levels"][0][:20] if len(book["levels"]) > 0 else []
        asks = book["levels"][1][:20] if len(book["levels"]) > 1 else []
        result["bid_liquidity"] = [(float(b["px"]), float(b["sz"])) for b in bids]
        result["ask_liquidity"] = [(float(a["px"]), float(a["sz"])) for a in asks]
        total_bid_sz = sum(float(b["sz"]) for b in bids)
        total_ask_sz = sum(float(a["sz"]) for a in asks)
        print(f"    Orderbook: {total_bid_sz:.2f} BTC bids, {total_ask_sz:.2f} BTC asks (top 20)")

    return result


# ============================================================================
# FEAR & GREED INDEX (alternative.me - free)
# ============================================================================

def fetch_fear_greed(days=30):
    """Fetch Fear & Greed Index from alternative.me."""
    print("  [Fear & Greed] Fetching...")
    data = http_get(f"https://api.alternative.me/fng/?limit={days}&format=json")
    if data:
        entries = data.get("data", [])
        print(f"    Got {len(entries)} days")
        if entries:
            latest = entries[0]
            print(f"    Latest: {latest.get('value')} ({latest.get('value_classification')})")
        return entries
    return []


# ============================================================================
# LIQUIDATION LEVEL CALCULATOR
# ============================================================================

# Leverage distribution weights (estimated from typical crypto futures markets)
# Based on: Binance data shows ~60% use 1-10x, ~25% use 10-25x, ~10% use 25-50x, ~5% use 50-100x
LEVERAGE_TIERS = [
    # (leverage, weight_pct, label)
    (5,   0.20, "5x"),
    (10,  0.30, "10x"),
    (25,  0.25, "25x"),
    (50,  0.15, "50x"),
    (100, 0.10, "100x"),
]


def calculate_liquidation_levels(market_data):
    """
    Calculate estimated liquidation levels based on real market data.

    Methodology (similar to Coinglass Liquidation Map):
    1. Take current price as entry reference
    2. For each leverage tier, calculate where positions would be liquidated
    3. Weight by estimated leverage distribution and long/short ratio
    4. The result: price levels with estimated $ liquidation volume

    Liquidation price formula:
      Long:  liq_price = entry_price * (1 - 1/leverage * (1 - maintenance_margin_rate))
      Short: liq_price = entry_price * (1 + 1/leverage * (1 - maintenance_margin_rate))

    We use maintenance_margin_rate â 0.5% for BTC (Binance standard)
    """
    print("\n--- Calculating Liquidation Levels ---")

    price = market_data.get("price") or market_data.get("hl_oracle_price", 70000)
    oi_btc = market_data.get("open_interest_btc", 0) + market_data.get("hl_open_interest", 0)
    oi_usd = oi_btc * price

    # Long/Short split from Binance ratios
    long_pct = market_data.get("top_long_pct", 0.52)
    short_pct = market_data.get("top_short_pct", 0.48)

    long_oi_usd = oi_usd * long_pct
    short_oi_usd = oi_usd * short_pct

    print(f"  Current Price: ${price:,.2f}")
    print(f"  Total OI: {oi_btc:,.2f} BTC (${oi_usd:,.0f})")
    print(f"  Long OI: ${long_oi_usd:,.0f} ({long_pct:.1%})")
    print(f"  Short OI: ${short_oi_usd:,.0f} ({short_pct:.1%})")

    # Maintenance margin rate (Binance standard for BTC)
    mmr = 0.005

    long_levels = []   # [(price, usd_volume)]
    short_levels = []  # [(price, usd_volume)]

    for leverage, weight, label in LEVERAGE_TIERS:
        # Estimated OI at this leverage tier
        long_vol = long_oi_usd * weight
        short_vol = short_oi_usd * weight

        # Long liquidation price (below current price)
        long_liq = price * (1 - (1 / leverage) * (1 - mmr))
        # Short liquidation price (above current price)
        short_liq = price * (1 + (1 / leverage) * (1 - mmr))

        long_levels.append((round(long_liq, 2), round(long_vol, 2), label))
        short_levels.append((round(short_liq, 2), round(short_vol, 2), label))

        print(f"  {label}: Long liq @ ${long_liq:,.0f} (${long_vol:,.0f}) | Short liq @ ${short_liq:,.0f} (${short_vol:,.0f})")

    # Also add intermediate levels based on recent price action
    # These create a "distribution" effect similar to the Coinglass heatmap
    # by assuming entries happened at different price points over recent range
    funding = market_data.get("funding_rate", 0)
    price_change = market_data.get("price_change_pct", 0)

    # Additional levels: assume entries at +/- 1%, 2%, 5% from current price
    offsets = [0.01, 0.02, 0.03, 0.05]
    for offset in offsets:
        entry_above = price * (1 + offset)
        entry_below = price * (1 - offset)

        for leverage, weight, label in LEVERAGE_TIERS:
            # Weight reduces with distance from current price
            dist_weight = weight * (1 - offset * 5)  # decay
            if dist_weight <= 0:
                continue

            vol_long = long_oi_usd * dist_weight * 0.15  # 15% per offset bucket
            vol_short = short_oi_usd * dist_weight * 0.15

            # Longs entered above -> liq further below
            liq_long_above = entry_above * (1 - (1 / leverage) * (1 - mmr))
            # Shorts entered below -> liq further above
            liq_short_below = entry_below * (1 + (1 / leverage) * (1 - mmr))

            long_levels.append((round(liq_long_above, 2), round(vol_long, 2), f"{label}+{offset:.0%}"))
            short_levels.append((round(liq_short_below, 2), round(vol_short, 2), f"{label}-{offset:.0%}"))

    # Sort and aggregate nearby levels (within 0.1% of each other)
    long_levels = aggregate_levels(long_levels, price)
    short_levels = aggregate_levels(short_levels, price)

    return {
        "price": price,
        "long_levels": long_levels,   # sorted by volume desc
        "short_levels": short_levels,  # sorted by volume desc
        "oi_btc": oi_btc,
        "oi_usd": oi_usd,
        "long_pct": long_pct,
        "short_pct": short_pct,
        "funding": funding,
    }


def aggregate_levels(levels, ref_price):
    """Aggregate nearby liquidation levels (within 0.2% of each other)."""
    if not levels:
        return []

    # Sort by price
    levels.sort(key=lambda x: x[0])

    aggregated = []
    current_price = levels[0][0]
    current_vol = levels[0][1]
    threshold = ref_price * 0.002  # 0.2%

    for i in range(1, len(levels)):
        p, v, _ = levels[i]
        if abs(p - current_price) <= threshold:
            # Merge: weighted average price, sum volume
            total_vol = current_vol + v
            current_price = (current_price * current_vol + p * v) / total_vol if total_vol > 0 else p
            current_vol = total_vol
        else:
            aggregated.append((round(current_price, 2), round(current_vol, 2)))
            current_price = p
            current_vol = v

    aggregated.append((round(current_price, 2), round(current_vol, 2)))

    # Sort by volume descending, return top 20
    aggregated.sort(key=lambda x: x[1], reverse=True)
    return aggregated[:20]


# ============================================================================
# PINE SEEDS CSV OUTPUT
# ============================================================================

def levels_to_csv(levels, ref_price):
    """
    Encode up to 20 liquidation levels into Pine Seeds CSV format.
    Each daily row encodes 4 levels: open=price1, high=price2, low=price3, close=price4
    Volume = total USD volume of those 4 levels.
    5 rows = 20 levels max.
    """
    if not levels:
        today = datetime.now(timezone.utc).strftime("%Y%m%dT")
        return f"{today},0,0,0,0,0"

    today = datetime.now(timezone.utc)
    lines = []

    for group_idx in range(5):
        start = group_idx * 4
        group = levels[start:start + 4]
        if not group:
            break

        while len(group) < 4:
            group.append((0, 0))

        prices = [g[0] for g in group]
        total_vol = sum(g[1] for g in group)

        offset_date = today - timedelta(days=group_idx)
        d_str = offset_date.strftime("%Y%m%dT")
        lines.append(f"{d_str},{prices[0]},{prices[1]},{prices[2]},{prices[3]},{total_vol}")

    lines.reverse()  # ascending date order
    return "\n".join(lines)


def fear_greed_to_csv(entries):
    """Convert F&G data to Pine Seeds CSV."""
    lines = []
    for entry in reversed(entries):  # oldest first
        ts = int(entry.get("timestamp", 0))
        value = float(entry.get("value", 50))
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        d_str = dt.strftime("%Y%m%dT")
        lines.append(f"{d_str},{value},{value},{value},{value},0")
    return "\n".join(lines)


def market_data_to_csv(market_data):
    """
    Encode key market metrics into a single CSV row for Pine Seeds.
    open = funding_rate * 10000 (scaled for readability)
    high = long_pct * 100
    low = short_pct * 100
    close = OI in millions USD
    volume = 24h volume in millions USD
    """
    today = datetime.now(timezone.utc).strftime("%Y%m%dT")
    funding_scaled = market_data.get("funding", 0) * 100000  # e.g. 0.0001 -> 10
    long_pct = market_data.get("long_pct", 50) * 100
    short_pct = market_data.get("short_pct", 50) * 100
    oi_millions = market_data.get("oi_usd", 0) / 1_000_000
    vol_millions = market_data.get("volume_24h_usd", 0) / 1_000_000

    return f"{today},{funding_scaled:.4f},{long_pct:.2f},{short_pct:.2f},{oi_millions:.2f},{vol_millions:.2f}"


# ============================================================================
# FILE OUTPUT
# ============================================================================

def write_csv(filename, content):
    """Write CSV content to data/ directory."""
    path = Path("data") / filename
    path.parent.mkdir(exist_ok=True)

    if not content or not content.strip():
        today = datetime.now(timezone.utc).strftime("%Y%m%dT")
        content = f"{today},0,0,0,0,0"
        print(f"  {filename}: No data, writing placeholder")
    else:
        line_count = content.count("\n") + 1
        print(f"  {filename}: {line_count} lines, {len(content)} bytes")

    path.write_text(content)


def write_symbol_info():
    """Write symbol_info JSON for Pine Seeds."""
    info_dir = Path("symbol_info")
    info_dir.mkdir(exist_ok=True)

    info = {
        "BTC_LIQ_LONGS": {
            "symbol": "BTC_LIQ_LONGS",
            "currency": "USD",
            "description": "BTC Long Liquidation Levels (Binance+Hyperliquid)"
        },
        "BTC_LIQ_SHORTS": {
            "symbol": "BTC_LIQ_SHORTS",
            "currency": "USD",
            "description": "BTC Short Liquidation Levels (Binance+Hyperliquid)"
        },
        "BTC_FEAR_GREED": {
            "symbol": "BTC_FEAR_GREED",
            "currency": "USD",
            "description": "Crypto Fear & Greed Index (alternative.me)"
        },
        "BTC_MARKET_DATA": {
            "symbol": "BTC_MARKET_DATA",
            "currency": "USD",
            "description": "BTC Market Metrics (Funding, L/S Ratio, OI)"
        }
    }

    (info_dir / "coinglass-pine-seeds.json").write_text(json.dumps(info, indent=2))
    print("  symbol_info written")


# ============================================================================
# MAIN
# ============================================================================

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    print(f"{'='*60}")
    print(f"  Pine Seeds Data Update â {mode}")
    print(f"  Time: {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*60}")

    market_data = {}

    if mode in ("all", "liquidation"):
        print("\n--- Binance Data ---")
        binance_data = fetch_binance_data()
        market_data.update(binance_data)

        print("\n--- Hyperliquid Data ---")
        hl_data = fetch_hyperliquid_data()
        market_data.update(hl_data)

        # Calculate liquidation levels
        liq_data = calculate_liquidation_levels(market_data)
        market_data.update(liq_data)

        print(f"\n--- Writing CSVs ---")
        print(f"  Top Long Liq Levels (below price):")
        for p, v in liq_data["long_levels"][:5]:
            print(f"    ${p:>10,.0f}  vol ${v:>15,.0f}")

        print(f"  Top Short Liq Levels (above price):")
        for p, v in liq_data["short_levels"][:5]:
            print(f"    ${p:>10,.0f}  vol ${v:>15,.0f}")

        write_csv("BTC_LIQ_LONGS.csv", levels_to_csv(liq_data["long_levels"], liq_data["price"]))
        write_csv("BTC_LIQ_SHORTS.csv", levels_to_csv(liq_data["short_levels"], liq_data["price"]))
        write_csv("BTC_MARKET_DATA.csv", market_data_to_csv(market_data))

    if mode in ("all", "feargreed"):
        print("\n--- Fear & Greed Index ---")
        fg_entries = fetch_fear_greed(30)
        if fg_entries:
            write_csv("BTC_FEAR_GREED.csv", fear_greed_to_csv(fg_entries))
        else:
            write_csv("BTC_FEAR_GREED.csv", "")

    write_symbol_info()
    print(f"\n{'='*60}")
    print("  Done!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
