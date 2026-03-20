# BTC Liquidation Levels → TradingView (Coinglass Real Data)

## Was macht das?
Echte **Coinglass Liquidation Heatmap Model 3** Daten werden alle 15 Minuten
automatisch über GitHub Actions abgerufen und in ein Format konvertiert, das
direkt in den TradingView Pine Script Indikator eingefügt werden kann.

**NEU in v6: Echte Coinglass-Daten!** Kein API-Key nötig — die Daten werden
direkt von der Coinglass-Website geholt (gleiche Daten wie die Heatmap-Seite).

**Datenquellen:**
- **Coinglass Model 3 Heatmap** (Binance BTC/USDT): Echte Liquidation-Levels
- **Binance Futures API** (kostenlos): Open Interest, Long/Short Ratios, Funding Rate
- **Hyperliquid API** (kostenlos): OI, Funding
- **alternative.me** (kostenlos): Fear & Greed Index

## So funktioniert's

### Daten-Pipeline
```
Coinglass Model 3 API
     ↓ (AES-128-ECB verschlüsselt)
GitHub Action: fetch_liquidations.py
     ↓ (Entschlüsselung → Gzip → JSON)
Liquidation-Cluster berechnen
     ↓
data/COINGLASS_LEVELS.pine  ← In TradingView einfügen!
data/latest_levels.json     ← JSON für andere Zwecke
data/BTC_LIQ_*.csv          ← Pine Seeds Format (für wenn TV das reaktiviert)
```

### Was sind die "Levels"?
Aus den ~126.000 Datenpunkten der Coinglass Heatmap werden die **Top 20 stärksten
Liquidation-Cluster** berechnet — die Preislevel, an denen das meiste Liquidationsvolumen
konzentriert ist. Das sind reale Support/Resistance-Zonen, die von echten Marktdaten
abgeleitet sind.

## Setup-Schritte

### 1. GitHub Repository einrichten
1. Stelle sicher, dass alle Dateien im Repo sind:
   - `fetch_liquidations.py`
   - `.github/workflows/update_data.yml`
   - `SETUP.md`
   - `data/` (wird automatisch gefüllt)
   - `symbol_info/` (wird automatisch gefüllt)

### 2. GitHub Action testen
1. Gehe in dein Repo → Actions Tab
2. Du siehst "Update BTC Liquidation & Market Data"
3. Klicke "Run workflow" zum manuellen Testen
4. Prüfe ob `data/COINGLASS_LEVELS.pine` erstellt wird
5. Ab jetzt läuft es automatisch alle 15 Minuten

### 3. Levels in TradingView einfügen
1. Öffne `data/COINGLASS_LEVELS.pine` in deinem Repo
2. Kopiere die `array.from(...)` Zeilen
3. Öffne den Pine Script Editor in TradingView
4. Suche nach `var float[] cg_long_prices = array.new_float(0)`
5. Ersetze die leeren Arrays mit den kopierten Werten, z.B.:
   ```pinescript
   var float[] cg_long_prices = array.from(72500.50, 71200.30, 70000.00, ...)
   var float[] cg_long_vols   = array.from(1523400, 1201000, 985000, ...)
   var float[] cg_short_prices = array.from(76500.20, 78000.00, 80000.00, ...)
   var float[] cg_short_vols   = array.from(1845000, 1400000, 1100000, ...)
   ```
6. Speichere den Indikator
7. Das Dashboard zeigt "LIQ: CG LIVE" in grün wenn Daten aktiv sind

### 4. Levels aktualisieren
- Die GitHub Action holt alle 15 Minuten neue Daten
- Um den Indikator zu aktualisieren: Schritt 3 wiederholen
- **Tipp**: Setze ein Browser-Bookmark auf dein `COINGLASS_LEVELS.pine` Datei-Link
  für schnellen Zugriff

## Indicator Features

### Liquidation Display Modes
- **Heatmap**: Coinglass-ähnliche 2D-Heatmap (berechnet aus Chart-Daten)
- **Lines (Classic)**: Zeigt echte Coinglass-Liquidation-Levels als Linien

### Coinglass Real Data (Lines Mode)
- Top 20 Long-Liquidation-Cluster (rot, unter dem Preis)
- Top 20 Short-Liquidation-Cluster (grün, über dem Preis)
- Linienstärke = Volumen-Ranking (dickere = stärkere Cluster)
- Labels mit Preislevel und Volumen für Top 5

### Andere Features
- CME Gaps mit Altersanzeige
- Volume Imbalances (4H/Daily/Weekly)
- Chart Patterns (H&S, Wedges, Triangles, Channels)
- Fear & Greed Dashboard mit 10-Tage Sparkline
- RSI + 200D MA

## Daten-Format

### COINGLASS_LEVELS.pine
Pine Script Snippet mit `array.from()` — direkt copy-paste bereit:
- `cg_long_prices`: Preislevel der Long-Liquidation-Cluster
- `cg_long_vols`: Volumen pro Cluster
- `cg_short_prices` / `cg_short_vols`: Dasselbe für Shorts
- Sortiert nach Volumen (stärkster Cluster zuerst)

### latest_levels.json
JSON mit allen Levels und Metadaten — für eigene Skripte oder Bots.

### BTC_LIQ_LONGS.csv / BTC_LIQ_SHORTS.csv
Pine Seeds Format (für zukünftige Pine Seeds Kompatibilität):
- OHLCV-encodiert: 4 Levels pro Zeile, 5 Zeilen = 20 Levels

### BTC_MARKET_DATA.csv
- open = Funding Rate × 100.000
- high = Long %
- low = Short %
- close = Open Interest in Mio USD
- volume = 24h Volumen in Mio USD

### BTC_FEAR_GREED.csv
- OHLC = Fear & Greed Wert (0-100)

## Technische Details

### Coinglass API
- **Endpoint**: `fapi.coinglass.com/api/index/v6/liqHeatMap`
- **Verschlüsselung**: AES-128-ECB (Request + Response)
- **Komprimierung**: Gzip (Response nach Entschlüsselung)
- **Datenformat**: JSON mit ~370 Preislevel, ~576 Candles, ~126k Datenpunkte

### GitHub Actions
- 15-Min-Intervall = ~2880 runs/Monat × ~20s ≈ ~960 min (innerhalb Free Tier)
- Benötigt: `pycryptodome` (wird automatisch installiert)

## Troubleshooting

1. **"LIQ: CALC" statt "LIQ: CG LIVE"**: Arrays sind noch leer — COINGLASS_LEVELS.pine einfügen
2. **Action schlägt fehl**: Logs prüfen — meistens Netzwerkfehler oder Coinglass ändert API
3. **Leere COINGLASS_LEVELS.pine**: Coinglass war temporär nicht erreichbar, Fallback auf Binance
4. **Heatmap zeigt nichts**: "Show Liquidation Levels" und Display Mode "Heatmap" prüfen
5. **Lines zeigen nichts**: "Lines (Classic)" wählen + Coinglass-Arrays einfügen
