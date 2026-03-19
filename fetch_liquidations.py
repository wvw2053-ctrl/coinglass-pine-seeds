"""
Coinglass Liquidation Data -> TradingView Pine Seeds Format
Fetches BTC liquidation heatmap data from Coinglass API and converts
it to CSV format compatible with TradingView's request.seed() function.

Usage:
  python fetch_liquidations.py

Requires:
  - COINGLASS_API_KEY environment variable (get free key at coinglass.com/pricing)
  - pip install requests

Output:
  - data/BTC_LIQ_LONGS.csv  (long liquidation levels)
  - data/BTC_LIQ_SHORTS.csv (short liquidation levels)
"""

import os
import json
import requests
from datetime import datetime, timezone
from pathlib import Path

API_KEY = os.environ.get("COINGLASS_API_KEY", "")
BASE_URL = "https://open-api-v4.coinglass.com/api"

# Endpoints to try (v4 first, fallback to v3)
HEATMAP_ENDPOINTS = [
    f"{BASE_URL}/futures/liquidation/aggregated-heatmap/model3",
    f"{BASE_URL}/futures/liquidation/heatmap/model3",
    "https://open-api-v3.coinglass.com/api/futures/liquidation/model3/heatmap",
]

HEADERS = {
    "accept": "application/json",
    "CG-API-KEY": API_KEY,
    "coinglassSecret": API_KEY,  # v3 compat
}

def fetch_heatmap(symbol="BTC", range_type="4h"):
    """Fetch liquidation heatmap data from Coinglass."""
    params = {
        "symbol": symbol,
        "range": range_type,
    }

    for endpoint in HEATMAP_ENDPOINTS:
        try:
            resp = requests.get(endpoint, headers=HEADERS, params=params, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == "0" or data.get("success"):
                    print(f"OK: {endpoint}")
                    return data.get("data", data)
                else:
                    print(f"API error: {data.get('msg', data.get('message', 'unknown'))}")
            else:
                print(f"HTTP {resp.status_code} from {endpoint}")
        except Exception as e:
            print(f"Error fetching {endpoint}: {e}")

    return None


def fetch_liquidation_map(symbol="BTC"):
    """Fetch liquidation map (price levels with estimated liquidation volume)."""
    endpoint = f"{BASE_URL}/futures/liquidation/map"
    params = {"symbol": symbol}

    try:
        resp = requests.get(endpoint, headers=HEADERS, params=params, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == "0":
                return data.get("data", {})
    except Exception as e:
        print(f"Error fetching liq map: {e}")

    return None


def extract_levels(data):
    """
    Extract liquidation price levels from API response.
    Returns dict with 'longs' and 'shorts' lists of (price, volume) tuples.
    """
    longs = []
    shorts = []

    if data is None:
        return {"longs": longs, "shorts": shorts}

    # Handle different response formats
    if isinstance(data, dict):
        # Liquidation map format
        if "longs" in data and "shorts" in data:
            for item in data.get("longs", []):
                if isinstance(item, dict):
                    longs.append((float(item.get("price", 0)), float(item.get("vol", 0))))
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    longs.append((float(item[0]), float(item[1])))
            for item in data.get("shorts", []):
                if isinstance(item, dict):
                    shorts.append((float(item.get("price", 0)), float(item.get("vol", 0))))
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    shorts.append((float(item[0]), float(item[1])))

        # Heatmap format (y=prices, liq=liquidation values)
        elif "y" in data and "liq" in data:
            prices = data["y"]
            liq_values = data["liq"]
            for i, price in enumerate(prices):
                if i < len(liq_values):
                    vol = float(liq_values[i])
                    if vol > 0:
                        longs.append((float(price), vol))
                    elif vol < 0:
                        shorts.append((float(price), abs(vol)))

        # Nested data format
        elif "data" in data:
            return extract_levels(data["data"])

        # Array of price/liq objects
        elif "prices" in data:
            for item in data["prices"]:
                price = float(item.get("price", 0))
                long_vol = float(item.get("longVol", item.get("long_vol", 0)))
                short_vol = float(item.get("shortVol", item.get("short_vol", 0)))
                if long_vol > 0:
                    longs.append((price, long_vol))
                if short_vol > 0:
                    shorts.append((price, short_vol))

    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                price = float(item.get("price", item.get("p", 0)))
                vol = float(item.get("vol", item.get("v", item.get("liqVol", 0))))
                side = item.get("side", item.get("type", ""))
                if side in ("long", "buy", "1"):
                    longs.append((price, vol))
                elif side in ("short", "sell", "2"):
                    shorts.append((price, vol))

    # Sort by volume descending, keep top 20 levels
    longs.sort(key=lambda x: x[1], reverse=True)
    shorts.sort(key=lambda x: x[1], reverse=True)

    return {
        "longs": longs[:20],
        "shorts": shorts[:20],
    }


def levels_to_pine_csv(levels, side="longs"):
    """
    Convert liquidation levels to Pine Seeds CSV format.

    Pine Seeds format: YYYYMMDDT,open,high,low,close,volume

    Strategy: We encode MULTIPLE price levels into a single daily row.
    - open  = strongest liquidation level (highest volume)
    - high  = 2nd strongest level
    - low   = 3rd strongest level
    - close = 4th strongest level
    - volume = total liquidation volume across all levels

    Additional levels are stored in subsequent "days" offset by 1 day each.
    Pine Script reads them back using close[0], close[1], etc.
    """
    items = levels.get(side, [])
    if not items:
        return ""

    today = datetime.now(timezone.utc)
    date_str = today.strftime("%Y%m%dT")

    lines = []

    # Pack up to 5 groups of 4 levels each (= 20 levels total)
    for group_idx in range(5):
        start = group_idx * 4
        group = items[start:start + 4]
        if not group:
            break

        # Pad to 4 entries
        while len(group) < 4:
            group.append((0, 0))

        prices = [g[0] for g in group]
        total_vol = sum(g[1] for g in group)

        # Use date offset for each group (today, yesterday, etc.)
        from datetime import timedelta
        offset_date = today - timedelta(days=group_idx)
        d_str = offset_date.strftime("%Y%m%dT")

        line = f"{d_str},{prices[0]},{prices[1]},{prices[2]},{prices[3]},{total_vol}"
        lines.append(line)

    # Pine seeds needs ascending date order
    lines.reverse()
    return "\n".join(lines)


def write_csv(filename, content):
    """Write CSV content to data/ directory."""
    path = Path("data") / filename
    path.parent.mkdir(exist_ok=True)

    if not content.strip():
        print(f"  No data for {filename}, writing placeholder")
        today = datetime.now(timezone.utc).strftime("%Y%m%dT")
        content = f"{today},0,0,0,0,0"

    path.write_text(content)
    print(f"  Written: {path} ({len(content)} bytes)")


def write_symbol_info():
    """Write symbol_info JSON for Pine Seeds."""
    info_dir = Path("symbol_info")
    info_dir.mkdir(exist_ok=True)

    # Repo name should match your GitHub repo name
    info = {
        "BTC_LIQ_LONGS": {
            "symbol": "BTC_LIQ_LONGS",
            "currency": "USD",
            "description": "BTC Long Liquidation Levels (Coinglass)"
        },
        "BTC_LIQ_SHORTS": {
            "symbol": "BTC_LIQ_SHORTS",
            "currency": "USD",
            "description": "BTC Short Liquidation Levels (Coinglass)"
        }
    }

    info_path = info_dir / "coinglass-pine-seeds.json"
    info_path.write_text(json.dumps(info, indent=2))
    print(f"  Written: {info_path}")


def main():
    if not API_KEY:
        print("ERROR: Set COINGLASS_API_KEY environment variable")
        print("Get your free key at: https://www.coinglass.com/pricing")
        return

    print("=== Coinglass -> Pine Seeds ===")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")

    # Try heatmap first, then liquidation map
    print("\nFetching heatmap data...")
    data = fetch_heatmap("BTC", "4h")

    if data is None:
        print("Heatmap failed, trying liquidation map...")
        data = fetch_liquidation_map("BTC")

    levels = extract_levels(data)

    print(f"\nFound {len(levels['longs'])} long levels, {len(levels['shorts'])} short levels")

    if levels["longs"]:
        print("\nTop long liquidation levels:")
        for price, vol in levels["longs"][:5]:
            print(f"  ${price:,.0f}  vol={vol:,.0f}")

    if levels["shorts"]:
        print("\nTop short liquidation levels:")
        for price, vol in levels["shorts"][:5]:
            print(f"  ${price:,.0f}  vol={vol:,.0f}")

    # Write CSVs
    print("\nWriting CSV files...")
    write_csv("BTC_LIQ_LONGS.csv", levels_to_pine_csv(levels, "longs"))
    write_csv("BTC_LIQ_SHORTS.csv", levels_to_pine_csv(levels, "shorts"))
    write_symbol_info()

    print("\nDone!")


if __name__ == "__main__":
    main()
