# BTC Liquidation Levels → TradingView Pine Seeds

## Was macht das?
Echte Marktdaten von **Binance** und **Hyperliquid** (kostenlos, kein API Key nötig!)
werden alle 15 Minuten automatisch geholt und daraus realistische Liquidation-Levels
berechnet — genau wie Coinglass es intern für ihre Liquidation Map macht.

**Neu in v5: Liquidation Heatmap** — Coinglass-ähnliche 2D-Heatmap direkt in TradingView!
Berechnet aus Chart-Daten, kein externes Daten-Dependency nötig.

**Datenquellen:**
- **Binance Futures API** (kostenlos): Open Interest, Long/Short Ratios, Funding Rate
- **Hyperliquid API** (kostenlos): OI, Orderbook-Daten, Funding
- **alternative.me** (kostenlos): Fear & Greed Index

**Berechnung der Liquidation-Levels:**
Basierend auf echtem Open Interest und Long/Short-Verteilung werden für jede
Leverage-Stufe (5x, 10x, 25x, 50x, 100x) die Preise berechnet, an denen
Positionen liquidiert würden. Die Levels werden nach geschätztem USD-Volumen
gewichtet — die dicksten Cluster sind die wichtigsten.

## Indicator Features

### Liquidation Heatmap (NEU)
- **Display Mode**: Wähle zwischen "Heatmap" (Coinglass-Style) oder "Lines (Classic)"
- **Heatmap Interval**: 1 day, **3 day** (default), 7 day, 14 day, 30 day
- **Heatmap Resolution**: 30-100 Preisbänder (default 60, höher = feiner)
- **Price Range %**: Abdeckung ober-/unterhalb des Preises (default 30%)
- **Liquidity Threshold**: Wie bei Coinglass (0.9 = zeige 90% der Daten, filtere schwächste 10%)
- **Farbgradient**: Lila (schwach) → Blau → Cyan → Grün → Gelb (stärkste Cluster)
- Adaptiert automatisch zur Chart-Timeframe (1m, 5m, 15m, 1h, 4h, D)
- Die Heatmap wird komplett aus Chart-Daten berechnet — kein Pine Seeds nötig!

### Andere Features
- CME Gaps mit Altersanzeige
- Volume Imbalances (4H/Daily/Weekly)
- Chart Patterns (H&S, Wedges, Triangles, Channels)
- Fear & Greed Dashboard mit 10-Tage Sparkline
- RSI + 200D MA

## Setup-Schritte

### 1. GitHub Repository erstellen
1. Erstelle ein neues GitHub Repo: `coinglass-pine-seeds`
2. Kopiere alle Dateien aus diesem Ordner:
   - `fetch_liquidations.py`
   - `.github/workflows/update_data.yml`
   - `SETUP.md`
3. Erstelle die Ordner `data/` und `symbol_info/` (können leer sein)

### 2. GitHub Action testen
1. Gehe in dein Repo → Actions Tab
2. Du siehst "Update BTC Liquidation & Market Data"
3. Klicke "Run workflow" zum manuellen Testen
4. Prüfe ob `data/` und `symbol_info/` gefüllt werden
5. Ab jetzt läuft es automatisch alle 15 Minuten

**Kein API Key nötig!** Alle verwendeten APIs sind komplett kostenlos.

### 3. Pine Script konfigurieren
Im `Pique Crypto - Community Indicator.pine` ist der GitHub-Username bereits eingetragen.
Falls du ihn ändern musst, suche nach `request.seed("wvw2053-ctrl/coinglass-pine-seeds"`:

```pinescript
seed_long_1 = request.seed("wvw2053-ctrl/coinglass-pine-seeds", "BTC_LIQ_LONGS", close)
```

Es gibt ~14 Zeilen mit `request.seed()` — alle müssen den gleichen Username haben.

### 4. In TradingView laden
1. Öffne TradingView → Pine Editor
2. Füge den gesamten `Pique Crypto - Community Indicator.pine` Code ein
3. In den Indicator-Settings:
   - **Display Mode**: "Heatmap" für die neue Coinglass-ähnliche Ansicht
   - **Heatmap Interval**: Zeitfenster wählen (default: 3 day)
   - **Data Source** (nur für Lines-Mode): "Pine Seeds (Real Data)" auswählen
4. Das Dashboard zeigt "LIQ: LIVE" in grün wenn Pine Seeds aktiv sind

## Daten-Format

### BTC_LIQ_LONGS.csv / BTC_LIQ_SHORTS.csv
Jede Zeile encodiert 4 Liquidation-Preis-Levels:
- open = stärkstes Level (höchstes geschätztes Volumen)
- high = 2. stärkstes
- low = 3. stärkstes
- close = 4. stärkstes
- volume = Gesamtes USD-Volumen dieser 4 Levels

5 Zeilen = bis zu 20 Levels, sortiert nach Volumen.

### BTC_MARKET_DATA.csv
- open = Funding Rate × 100.000 (skaliert)
- high = Long % (z.B. 52.10 = 52.1% Long)
- low = Short % (z.B. 47.90 = 47.9% Short)
- close = Open Interest in Millionen USD
- volume = 24h Volumen in Millionen USD

### BTC_FEAR_GREED.csv
- OHLC = Fear & Greed Wert (0-100)
- volume = 0

## Wichtige Hinweise

- **Heatmap braucht kein Pine Seeds**: Die Heatmap berechnet alles lokal aus Chart-Daten
- **Lines-Mode nutzt Pine Seeds**: Für echte OI-basierte Levels (wenn verfügbar)
- **Keine externen Dependencies**: Das Python Script nutzt nur `urllib` (stdlib)
- **GitHub Actions Minutes**: 15-Min-Intervall = ~2880 runs/Monat × ~15s ≈ 720 min
  (weit innerhalb der 2000 min Free Tier)
- **Pine Seeds Delay**: TradingView cached Daten, Updates können 5-30 Min dauern
- **Fallback**: Wenn Pine Seeds nicht verfügbar sind, nutzt der Lines-Mode die
  eingebaute Berechnung (Volume + ATR basiert)

## Troubleshooting

1. **"LIQ: CALC" statt "LIQ: LIVE"**: Username prüfen oder GitHub Action schauen
2. **Action schlägt fehl**: Schau in die Action Logs — meistens ist es ein Netzwerkfehler
3. **Leere CSVs**: Binance/Hyperliquid API kann temporär down sein
4. **TradingView zeigt keine Daten**: `request.seed()` braucht den exakten Repo-Namen
5. **Heatmap zeigt nichts**: Prüfe ob "Show Liquidation Levels" aktiviert ist und Display Mode auf "Heatmap" steht
6. **Heatmap zu spärlich**: Threshold runter setzen (z.B. 0.7) oder Resolution hochsetzen
