# BTC Liquidation Levels â TradingView Pine Seeds

## Was macht das?
Echte Marktdaten von **Binance** und **Hyperliquid** (kostenlos, kein API Key nÃ¶tig!)
werden alle 15 Minuten automatisch geholt und daraus realistische Liquidation-Levels
berechnet â genau wie Coinglass es intern fÃ¼r ihre Liquidation Map macht.

**Datenquellen:**
- **Binance Futures API** (kostenlos): Open Interest, Long/Short Ratios, Funding Rate
- **Hyperliquid API** (kostenlos): OI, Orderbook-Daten, Funding
- **alternative.me** (kostenlos): Fear & Greed Index

**Berechnung der Liquidation-Levels:**
Basierend auf echtem Open Interest und Long/Short-Verteilung werden fÃ¼r jede
Leverage-Stufe (5x, 10x, 25x, 50x, 100x) die Preise berechnet, an denen
Positionen liquidiert wÃ¼rden. Die Levels werden nach geschÃ¤tztem USD-Volumen
gewichtet â die dicksten Cluster sind die wichtigsten.

## Setup-Schritte

### 1. GitHub Repository erstellen
1. Erstelle ein neues GitHub Repo: `coinglass-pine-seeds`
2. Kopiere alle Dateien aus diesem Ordner:
   - `fetch_liquidations.py`
   - `.github/workflows/update_data.yml`
3. Erstelle die Ordner `data/` und `symbol_info/` (kÃ¶nnen leer sein)

### 2. GitHub Action testen
1. Gehe in dein Repo â Actions Tab
2. Du siehst "Update BTC Liquidation & Market Data"
3. Klicke "Run workflow" zum manuellen Testen
4. PrÃ¼fe ob `data/` und `symbol_info/` gefÃ¼llt werden
5. Ab jetzt lÃ¤uft es automatisch alle 15 Minuten

**Kein API Key nÃ¶tig!** Alle verwendeten APIs sind komplett kostenlos.

### 3. Pine Script konfigurieren
Im `BTC_MegaIndicator.pine` musst du deinen GitHub-Username eintragen.
Suche nach `YOUR_GITHUB_USERNAME` und ersetze es mit deinem Username:

```pinescript
// VORHER:
seed_long_1 = request.seed("YOUR_GITHUB_USERNAME/coinglass-pine-seeds", "BTC_LIQ_LONGS", close)

// NACHHER (Beispiel fÃ¼r User "m3tal"):
seed_long_1 = request.seed("m3tal/coinglass-pine-seeds", "BTC_LIQ_LONGS", close)
```

Es gibt ~14 Zeilen mit `request.seed()` â alle mÃ¼ssen geÃ¤ndert werden.

### 4. In TradingView laden
1. Ãffne TradingView â Pine Editor
2. FÃ¼ge den gesamten `BTC_MegaIndicator.pine` Code ein
3. In den Indicator-Settings:
   - **Data Source**: "Pine Seeds (Real Data)" auswÃ¤hlen
   - **GitHub Username**: Deinen Username eintragen
4. Das Dashboard zeigt "LIQ: LIVE" in grÃ¼n wenn die Daten verfÃ¼gbar sind

## Daten-Format

### BTC_LIQ_LONGS.csv / BTC_LIQ_SHORTS.csv
Jede Zeile encodiert 4 Liquidation-Preis-Levels:
- open = stÃ¤rkstes Level (hÃ¶chstes geschÃ¤tztes Volumen)
- high = 2. stÃ¤rkstes
- low = 3. stÃ¤rkstes
- close = 4. stÃ¤rkstes
- volume = Gesamtes USD-Volumen dieser 4 Levels

5 Zeilen = bis zu 20 Levels, sortiert nach Volumen.

### BTC_MARKET_DATA.csv
- open = Funding Rate Ã 100.000 (skaliert)
- high = Long % (z.B. 52.10 = 52.1% Long)
- low = Short % (z.B. 47.90 = 47.9% Short)
- close = Open Interest in Millionen USD
- volume = 24h Volumen in Millionen USD

### BTC_FEAR_GREED.csv
- OHLC = Fear & Greed Wert (0-100)
- volume = 0

## Wichtige Hinweise

- **Keine externen Dependencies**: Das Python Script nutzt nur `urllib` (stdlib)
- **GitHub Actions Minutes**: 15-Min-Intervall = ~2880 runs/Monat Ã ~15s â 720 min
  (weit innerhalb der 2000 min Free Tier)
- **Pine Seeds Delay**: TradingView cached Daten, Updates kÃ¶nnen 5-30 Min dauern
- **Fallback**: Wenn Pine Seeds nicht verfÃ¼gbar sind, nutzt der Indicator die
  eingebaute Berechnung (Volume + ATR basiert)

## Troubleshooting

1. **"LIQ: CALC" statt "LIQ: LIVE"**: Username prÃ¼fen oder GitHub Action schauen
2. **Action schlÃ¤gt fehl**: Schau in die Action Logs â meistens ist es ein Netzwerkfehler
3. **Leere CSVs**: Binance/Hyperliquid API kann temporÃ¤r down sein
4. **TradingView zeigt keine Daten**: `request.seed()` braucht den exakten Repo-Namen
