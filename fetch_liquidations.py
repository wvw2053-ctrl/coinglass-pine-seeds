"""
Real Coinglass Liquidation Heatmap â TradingView Pine Seeds
============================================================
Fetches REAL liquidation heatmap data from Coinglass (Model 3)
and converts it to Pine Seeds CSV format for TradingView.

Also fetches market metrics from Binance/Hyperliquid (free, no API key)
and Fear & Greed Index.

Data pipeline:
  Coinglass internal API â AES decrypt â gzip decompress â JSON
  â aggregate into price bands â Pine Seeds CSV

Requirements: pip install pycryptodome
"""

import json
import sys
import time
import gzip
import hmac
import hashlib
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path
from base64 import b64decode, b64encode, b32decode

# Python 3 stdlib for HTTP
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# AES encryption (pycryptodome)
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


# ============================================================================
# AES ENCRYPTION / DECRYPTION
# ============================================================================

AES_KEY = b"1f68efd73f8d4921acc0dead41dd39bc"  # 32-byte key = AES-256 (updated 2026-03-20)
TOTP_SECRET = "I65VU7K5ZQL7WB4E"  # Base32-encoded TOTP secret


def totp_generate(secret_b32: str, timestamp: int, step: int = 30, digits: int = 6) -> str:
    """Generate TOTP code (RFC 6238) using stdlib only."""
    key = b32decode(secret_b32, casefold=True)
    counter = struct.pack(">Q", timestamp // step)
    hmac_hash = hmac.new(key, counter, hashlib.sha1).digest()
    offset = hmac_hash[-1] & 0x0F
    code = struct.unpack(">I", hmac_hash[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10 ** digits)).zfill(digits)


def aes_ecb_encrypt(plaintext: str) -> str:
    """AES-256-ECB encrypt with PKCS7 padding, return base64."""
    cipher = AES.new(AES_KEY, AES.MODE_ECB)
    padded = pad(plaintext.encode("utf-8"), AES.block_size)
    encrypted = cipher.encrypt(padded)
    return b64encode(encrypted).decode("utf-8")


def aes_ecb_decrypt(ciphertext_b64: str) -> bytes:
    """AES-256-ECB decrypt, return raw bytes (PKCS7 unpadded)."""
    cipher = AES.new(AES_KEY, AES.MODE_ECB)
    raw = b64decode(ciphertext_b64)
    decrypted = cipher.decrypt(raw)
    return unpad(decrypted, AES.block_size)


# ============================================================================
# COINGLASS HEATMAP API
# ============================================================================

def generate_data_param() -> str:
    """Generate the encrypted 'data' query parameter for Coinglass API."""
    ts = int(time.time())
    otp = totp_generate(TOTP_SECRET, ts, step=30)
    plaintext = f"{ts},{otp}"
    return aes_ecb_encrypt(plaintext)


def fetch_coinglass_heatmap(symbol="Binance_BTCUSDT", time_range="48h"):
    """
    Fetch real liquidation heatmap data from Coinglass.

    Args:
        symbol: Exchange_Pair (e.g., "Binance_BTCUSDT")
        time_range: "24h", "48h", "72h", "1w", "2w", "1m"

    Returns:
        dict: y (price levels), prices (candles), liq (liquidation data),
              rangeHigh, rangeLow, instrument, updateTime
    """
    print(f"  [Coinglass] Fetching heatmap: {symbol} / {time_range}")

    data_param = generate_data_param()
    url = (
        f"https://fapi.coinglass.com/api/index/v6/liqHeatMap"
        f"?merge=true&symbol={symbol}&range={time_range}&cp=false"
        f"&data={data_param}"
    )

    req = Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.coinglass.com/",
        "Origin": "https://www.coinglass.com",
    })

    try:
        with urlopen(req, timeout=30) as resp:
            raw = json.loads(resp.read().decode())
    except (URLError, HTTPError) as e:
        print(f"    Error fetching: {e}")
        return None

    if raw.get("code") != "0" or not raw.get("success"):
        print(f"    API error: code={raw.get('code')}, msg={raw.get('msg')}")
        return None

    encrypted_data = raw["data"]
    print(f"    Got encrypted response: {len(encrypted_data)} chars")

    # Decrypt AES-128-ECB
    try:
        decrypted_bytes = aes_ecb_decrypt(encrypted_data)
    except Exception as e:
        print(f"    Decrypt error: {e}")
        return None

    # The decrypted data is hex-encoded gzip
    try:
        hex_str = decrypted_bytes.decode("utf-8")
        gz_bytes = bytes.fromhex(hex_str)
        json_str = gzip.decompress(gz_bytes).decode("utf-8")
        data = json.loads(json_str)
    except Exception as e:
        print(f"    Decompress error: {e}")
        return None

    print(f"    Decoded: {len(data.get('y', []))} price levels, "
          f"{len(data.get('prices', []))} candles, "
          f"{len(data.get('liq', []))} liq points")
    print(f"    Price range: ${data.get('rangeLow', 0):,.0f} - ${data.get('rangeHigh', 0):,.0f}")

    return data


# ============================================================================
# HEATMAP DATA PROCESSING
# ============================================================================

def process_heatmap_for_pine_seeds(heatmap_data):
    """
    Process raw Coinglass heatmap data into aggregated liquidation clusters.

    Returns:
        dict with 'long_levels' and 'short_levels' (price, volume) tuples,
        plus metadata.
    """
    y_prices = heatmap_data["y"]
    candles = heatmap_data["prices"]
    liq_data = heatmap_data["liq"]
    range_high = heatmap_data["rangeHigh"]
    range_low = heatmap_data["rangeLow"]

    current_price = float(candles[-1][4]) if candles else (range_high + range_low) / 2
    print(f"    Current price: ${current_price:,.2f}")

    # Aggregate liquidation volumes by price level
    price_volumes = {}
    for entry in liq_data:
        y_idx = entry[0]
        vol = entry[2]
        price_volumes[y_idx] = price_volumes.get(y_idx, 0) + vol

    # Split into longs (below price) and shorts (above price)
    long_levels = []
    short_levels = []

    for y_idx, total_vol in price_volumes.items():
        if y_idx < len(y_prices):
            price = y_prices[y_idx]
            if price < current_price:
                long_levels.append((price, total_vol))
            else:
                short_levels.append((price, total_vol))

    # Sort by volume descending
    long_levels.sort(key=lambda x: x[1], reverse=True)
    short_levels.sort(key=lambda x: x[1], reverse=True)

    # Aggregate nearby levels (within 0.3%)
    long_bands = _aggregate_nearby(long_levels, current_price)
    short_bands = _aggregate_nearby(short_levels, current_price)

    print(f"    Long clusters: {len(long_bands)} | Short clusters: {len(short_bands)}")
    if long_bands:
        print(f"    Top long: ${long_bands[0][0]:,.0f} (vol: {long_bands[0][1]:,.0f})")
    if short_bands:
        print(f"    Top short: ${short_bands[0][0]:,.0f} (vol: {short_bands[0][1]:,.0f})")

    return {
        "long_levels": long_bands[:20],
        "short_levels": short_bands[:20],
        "current_price": current_price,
        "range_high": range_high,
        "range_low": range_low,
        "num_price_levels": len(y_prices),
        "num_candles": len(candles),
        "num_liq_points": len(liq_data),
    }


def _aggregate_nearby(levels, ref_price, max_bands=30):
    """Merge nearby price levels (within 0.3%) and return top N by volume."""
    if not levels:
        return []

    sorted_levels = sorted(levels, key=lambda x: x[0])
    threshold = ref_price * 0.003

    bands = []
    cur_p, cur_v = sorted_levels[0]
    for p, v in sorted_levels[1:]:
        if abs(p - cur_p) <= threshold:
            total = cur_v + v
            cur_p = (cur_p * cur_v + p * v) / total if total > 0 else p
            cur_v = total
        else:
            bands.append((round(cur_p, 2), round(cur_v, 2)))
            cur_p, cur_v = p, v
    bands.append((round(cur_p, 2), round(cur_v, 2)))

    bands.sort(key=lambda x: x[1], reverse=True)
    return bands[:max_bands]


# ============================================================================
# HTTP HELPERS
# ============================================================================

def http_get(url, timeout=15):
    req = Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "PineSeedsBot/1.0",
    })
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except (URLError, HTTPError) as e:
        print(f"  GET {url[:80]}... -> Error: {e}")
        return None


def http_post(url, payload, timeout=15):
    data = json.dumps(payload).encode()
    req = Request(url, data=data, headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "PineSeedsBot/1.0",
    })
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except (URLError, HTTPError) as e:
        print(f"  POST {url[:80]}... -> Error: {e}")
        return None


# ============================================================================
# BINANCE / HYPERLIQUID / FEAR & GREED
# ============================================================================

def fetch_binance_data():
    print("  [Binance] Fetching market data...")
    result = {}

    ticker = http_get("https://fapi.binance.com/fapi/v1/ticker/price?symbol=BTCUSDT")
    if ticker:
        result["price"] = float(ticker["price"])
        print(f"    Price: ${result['price']:,.2f}")

    oi = http_get("https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT")
    if oi:
        result["open_interest_btc"] = float(oi["openInterest"])

    tlsr = http_get("https://fapi.binance.com/futures/data/topLongShortPositionRatio?symbol=BTCUSDT&period=1h&limit=24")
    if tlsr and len(tlsr) > 0:
        latest = tlsr[-1]
        result["top_long_pct"] = float(latest["longAccount"])
        result["top_short_pct"] = float(latest["shortAccount"])

    funding = http_get("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT")
    if funding:
        result["funding_rate"] = float(funding.get("lastFundingRate", 0))

    stats = http_get("https://fapi.binance.com/fapi/v1/ticker/24hr?symbol=BTCUSDT")
    if stats:
        result["volume_24h_usd"] = float(stats.get("quoteVolume", 0))

    return result


def fetch_hyperliquid_data():
    print("  [Hyperliquid] Fetching market data...")
    result = {}

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

    return result


def fetch_fear_greed(days=30):
    print("  [Fear & Greed] Fetching...")
    data = http_get(f"https://api.alternative.me/fng/?limit={days}&format=json")
    if data:
        entries = data.get("data", [])
        print(f"    Got {len(entries)} days")
        return entries
    return []


# ============================================================================
# PINE SEEDS CSV OUTPUT
# ============================================================================

def levels_to_csv(levels, ref_price):
    """
    Encode up to 20 liquidation levels into Pine Seeds CSV.
    Each row: 4 price levels in OHLC, total volume in V.
    5 rows = 20 levels max.
    """
    today = datetime.now(timezone.utc)
    if not levels:
        return today.strftime("%Y%m%dT") + ",0,0,0,0,0"

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
        d = (today - timedelta(days=group_idx)).strftime("%Y%m%dT")
        lines.append(f"{d},{prices[0]},{prices[1]},{prices[2]},{prices[3]},{total_vol}")

    lines.reverse()
    return "\n".join(lines)


def fear_greed_to_csv(entries):
    lines = []
    for entry in reversed(entries):
        ts = int(entry.get("timestamp", 0))
        value = float(entry.get("value", 50))
        d = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y%m%dT")
        lines.append(f"{d},{value},{value},{value},{value},0")
    return "\n".join(lines)


def market_data_to_csv(market_data):
    today = datetime.now(timezone.utc).strftime("%Y%m%dT")
    funding_scaled = market_data.get("funding_rate", 0) * 100000
    long_pct = market_data.get("top_long_pct", 0.50) * 100
    short_pct = market_data.get("top_short_pct", 0.50) * 100

    price = market_data.get("price", 0)
    oi_btc = market_data.get("open_interest_btc", 0) + market_data.get("hl_open_interest", 0)
    oi_m = (oi_btc * price) / 1_000_000 if price > 0 else 0
    vol_m = market_data.get("volume_24h_usd", 0) / 1_000_000

    return f"{today},{funding_scaled:.4f},{long_pct:.2f},{short_pct:.2f},{oi_m:.2f},{vol_m:.2f}"


# ============================================================================
# FILE OUTPUT
# ============================================================================

def write_csv(filename, content):
    path = Path("data") / filename
    path.parent.mkdir(exist_ok=True)

    if not content or not content.strip():
        today = datetime.now(timezone.utc).strftime("%Y%m%dT")
        content = f"{today},0,0,0,0,0"
        print(f"  {filename}: No data, writing placeholder")
    else:
        print(f"  {filename}: {content.count(chr(10))+1} lines, {len(content)} bytes")

    path.write_text(content)


def write_symbol_info():
    info_dir = Path("symbol_info")
    info_dir.mkdir(exist_ok=True)

    info = {
        "BTC_LIQ_LONGS": {
            "symbol": "BTC_LIQ_LONGS",
            "currency": "USD",
            "description": "BTC Long Liquidation Levels (Coinglass Real Data)"
        },
        "BTC_LIQ_SHORTS": {
            "symbol": "BTC_LIQ_SHORTS",
            "currency": "USD",
            "description": "BTC Short Liquidation Levels (Coinglass Real Data)"
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


def write_levels_json(processed):
    """
    Write a JSON file with the latest liquidation levels.
    This can be served via GitHub Pages as a public API endpoint.
    """
    path = Path("data") / "latest_levels.json"
    path.parent.mkdir(exist_ok=True)

    output = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "price": processed["current_price"],
        "range_high": processed["range_high"],
        "range_low": processed["range_low"],
        "long_levels": [{"price": p, "volume": v} for p, v in processed["long_levels"]],
        "short_levels": [{"price": p, "volume": v} for p, v in processed["short_levels"]],
    }

    path.write_text(json.dumps(output, indent=2))
    print(f"  latest_levels.json written ({len(processed['long_levels'])} long, "
          f"{len(processed['short_levels'])} short clusters)")


def write_pine_levels(processed):
    """
    Generate a Pine Script snippet with real Coinglass liquidation levels
    hardcoded as arrays. Users can paste this into their indicator.
    """
    path = Path("data") / "COINGLASS_LEVELS.pine"
    path.parent.mkdir(exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    longs = processed["long_levels"][:20]
    shorts = processed["short_levels"][:20]

    long_prices = ", ".join(f"{p:.2f}" for p, _ in longs)
    long_vols = ", ".join(f"{v:.0f}" for _, v in longs)
    short_prices = ", ".join(f"{p:.2f}" for p, _ in shorts)
    short_vols = ", ".join(f"{v:.0f}" for _, v in shorts)

    pine = f"""// âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
// COINGLASS REAL LIQUIDATION LEVELS â Auto-generated
// Updated: {ts}
// Source: Coinglass Model 3 Heatmap (Binance BTC/USDT)
// Price at update: ${processed['current_price']:,.2f}
// âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

// --- Long Liquidation Clusters (below price) ---
// Sorted by volume descending â strongest clusters first
var float[] cg_long_prices = array.from({long_prices})
var float[] cg_long_vols   = array.from({long_vols})

// --- Short Liquidation Clusters (above price) ---
var float[] cg_short_prices = array.from({short_prices})
var float[] cg_short_vols   = array.from({short_vols})

// --- Metadata ---
var float cg_update_price = {processed['current_price']:.2f}
var float cg_range_high   = {processed['range_high']:.2f}
var float cg_range_low    = {processed['range_low']:.2f}
"""

    path.write_text(pine)
    print(f"  COINGLASS_LEVELS.pine written ({len(longs)} long, {len(shorts)} short levels)")


# ============================================================================
# MAIN
# ============================================================================

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    heatmap_range = sys.argv[2] if len(sys.argv) > 2 else "48h"

    print(f"{'='*60}")
    print(f"  Pine Seeds Data Update â {mode}")
    print(f"  Heatmap range: {heatmap_range}")
    print(f"  Time: {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*60}")

    market_data = {}

    if mode in ("all", "liquidation", "heatmap"):
        print("\n--- Coinglass Heatmap (Real Data) ---")
        heatmap = fetch_coinglass_heatmap("Binance_BTCUSDT", heatmap_range)

        if heatmap:
            processed = process_heatmap_for_pine_seeds(heatmap)

            print(f"\n--- Top Liquidation Clusters ---")
            print(f"  Longs (below price):")
            for p, v in processed["long_levels"][:5]:
                print(f"    ${p:>10,.0f}  vol {v:>15,.0f}")
            print(f"  Shorts (above price):")
            for p, v in processed["short_levels"][:5]:
                print(f"    ${p:>10,.0f}  vol {v:>15,.0f}")

            write_csv("BTC_LIQ_LONGS.csv",
                       levels_to_csv(processed["long_levels"], processed["current_price"]))
            write_csv("BTC_LIQ_SHORTS.csv",
                       levels_to_csv(processed["short_levels"], processed["current_price"]))

            # Also generate JSON + Pine Script snippet with real levels
            write_levels_json(processed)
            write_pine_levels(processed)
        else:
            print("  WARNING: Coinglass fetch failed, using Binance/Hyperliquid estimates")
            _fallback_liquidation(market_data)

    if mode in ("all", "market"):
        print("\n--- Binance Data ---")
        binance = fetch_binance_data()
        market_data.update(binance)
        print("\n--- Hyperliquid Data ---")
        hl = fetch_hyperliquid_data()
        market_data.update(hl)
        write_csv("BTC_MARKET_DATA.csv", market_data_to_csv(market_data))

    if mode in ("all", "feargreed"):
        print("\n--- Fear & Greed Index ---")
        fg = fetch_fear_greed(30)
        write_csv("BTC_FEAR_GREED.csv", fear_greed_to_csv(fg) if fg else "")

    write_symbol_info()
    print(f"\n{'='*60}")
    print("  Done!")
    print(f"{'='*60}")


def _fallback_liquidation(market_data):
    """Estimate liquidation levels from Binance/Hyperliquid when Coinglass fails."""
    binance = fetch_binance_data()
    market_data.update(binance)
    hl = fetch_hyperliquid_data()
    market_data.update(hl)

    price = market_data.get("price") or market_data.get("hl_oracle_price", 70000)
    oi_btc = market_data.get("open_interest_btc", 0) + market_data.get("hl_open_interest", 0)
    oi_usd = oi_btc * price
    long_pct = market_data.get("top_long_pct", 0.52)
    short_pct = market_data.get("top_short_pct", 0.48)
    mmr = 0.005

    tiers = [(5, 0.20), (10, 0.30), (25, 0.25), (50, 0.15), (100, 0.10)]
    longs, shorts = [], []
    for lev, wt in tiers:
        longs.append((round(price * (1 - (1/lev) * (1 - mmr)), 2), round(oi_usd * long_pct * wt, 2)))
        shorts.append((round(price * (1 + (1/lev) * (1 - mmr)), 2), round(oi_usd * short_pct * wt, 2)))

    longs.sort(key=lambda x: x[1], reverse=True)
    shorts.sort(key=lambda x: x[1], reverse=True)

    write_csv("BTC_LIQ_LONGS.csv", levels_to_csv(longs, price))
    write_csv("BTC_LIQ_SHORTS.csv", levels_to_csv(shorts, price))


if __name__ == "__main__":
    main()
