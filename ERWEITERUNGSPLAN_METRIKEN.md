# 📋 Erweiterungsplan: Neue Metriken für coin_metrics

## 🎯 Ziel
Erweiterung der `coin_metrics` Tabelle um zusätzliche Metriken zur Analyse von Trade-Verhalten:
- Netto-Volumen (Delta): Kauf- vs. Verkaufsdruck
- Volatilität: Preis-Schwankungen im Intervall
- Durchschnittliche Trade-Größe: Retail vs. Whale-Indikator
- Whale-Tracking: Große Trades (>1 SOL) separat tracken

## ⚠️ Wichtige Constraints
- ✅ **Keine erfundenen Zahlen** - Alle Werte basieren auf echten Trade-Daten
- ✅ **Nur Lesen** von `discovered_coins` (falls nötig für zusätzliche Kontext-Infos)
- ✅ **Nur Schreiben** in `coin_metrics`
- ✅ **Backward-kompatibel** - Bestehende Daten bleiben unverändert

---

## 📝 Schritt 1: Datenbank-Schema erweitern

### 1.1 SQL-Migration erstellen
**Datei:** `sql/add_advanced_metrics.sql`

```sql
-- Erweitere coin_metrics um neue Metriken
ALTER TABLE coin_metrics
    -- Netto-Volumen (Delta): buy_volume - sell_volume
    ADD COLUMN IF NOT EXISTS net_volume_sol NUMERIC(24, 9) DEFAULT 0,
    
    -- Volatilität: ((high - low) / open) * 100
    ADD COLUMN IF NOT EXISTS volatility_pct NUMERIC(10, 4) DEFAULT 0,
    
    -- Durchschnittliche Trade-Größe: volume / (num_buys + num_sells)
    ADD COLUMN IF NOT EXISTS avg_trade_size_sol NUMERIC(24, 9) DEFAULT 0,
    
    -- Whale Tracking (Trades >= 1.0 SOL)
    ADD COLUMN IF NOT EXISTS whale_buy_volume_sol NUMERIC(24, 9) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS whale_sell_volume_sol NUMERIC(24, 9) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS num_whale_buys INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS num_whale_sells INTEGER DEFAULT 0;
```

### 1.2 db_migration.py erweitern
**Datei:** `tracker/db_migration.py`

**Änderungen:**
- Neue Spalten zur `required_columns` Liste hinzufügen (Zeile 89-95)
- Migration-Logik für neue Spalten hinzufügen (Zeile 98-116)
- CREATE TABLE Statement erweitern (Zeile 52-75)

**Neue Spalten:**
```python
'net_volume_sol', 'volatility_pct', 'avg_trade_size_sol',
'whale_buy_volume_sol', 'whale_sell_volume_sol',
'num_whale_buys', 'num_whale_sells'
```

---

## 📝 Schritt 2: Buffer-Struktur erweitern

### 2.1 get_empty_buffer() erweitern
**Datei:** `tracker/main.py` (Zeile 281-287)

**Aktuell:**
```python
def get_empty_buffer(self):
    return {
        "open": None, "high": -1, "low": float("inf"), "close": 0,
        "vol": 0, "vol_buy": 0, "vol_sell": 0, "buys": 0, "sells": 0,
        "micro_trades": 0, "max_buy": 0, "max_sell": 0,
        "wallets": set(), "v_sol": 0, "mcap": 0
    }
```

**Neu:**
```python
def get_empty_buffer(self):
    return {
        "open": None, "high": -1, "low": float("inf"), "close": 0,
        "vol": 0, "vol_buy": 0, "vol_sell": 0, "buys": 0, "sells": 0,
        "micro_trades": 0, "max_buy": 0, "max_sell": 0,
        "wallets": set(), "v_sol": 0, "mcap": 0,
        # NEU: Whale-Tracking
        "whale_buy_vol": 0,
        "whale_sell_vol": 0,
        "whale_buys": 0,
        "whale_sells": 0
    }
```

---

## 📝 Schritt 3: Trade-Verarbeitung erweitern

### 3.1 Konstante hinzufügen
**Datei:** `tracker/main.py` (nach Zeile 28)

```python
WHALE_THRESHOLD_SOL = float(os.getenv("WHALE_THRESHOLD_SOL", "1.0"))  # Konfigurierbar über ENV
```

### 3.2 process_trade() erweitern
**Datei:** `tracker/main.py` (Zeile 716-744)

**Aktuell:**
```python
def process_trade(self, data):
    # ... bestehender Code ...
    if is_buy:
        buf["buys"] += 1
        buf["vol_buy"] += sol
        buf["max_buy"] = max(buf["max_buy"], sol)
    else:
        buf["sells"] += 1
        buf["vol_sell"] += sol
        buf["max_sell"] = max(buf["max_sell"], sol)
```

**Neu:**
```python
def process_trade(self, data):
    # ... bestehender Code bleibt gleich ...
    if is_buy:
        buf["buys"] += 1
        buf["vol_buy"] += sol
        buf["max_buy"] = max(buf["max_buy"], sol)
        # NEU: Whale-Tracking
        if sol >= WHALE_THRESHOLD_SOL:
            buf["whale_buy_vol"] += sol
            buf["whale_buys"] += 1
    else:
        buf["sells"] += 1
        buf["vol_sell"] += sol
        buf["max_sell"] = max(buf["max_sell"], sol)
        # NEU: Whale-Tracking
        if sol >= WHALE_THRESHOLD_SOL:
            buf["whale_sell_vol"] += sol
            buf["whale_sells"] += 1
```

---

## 📝 Schritt 4: Metriken-Berechnung erweitern

### 4.1 Berechnungsfunktion erstellen
**Datei:** `tracker/main.py` (neue Funktion nach `process_trade()`)

```python
def calculate_advanced_metrics(self, buf):
    """
    Berechnet erweiterte Metriken aus dem Buffer
    Alle Werte basieren auf echten Trade-Daten (keine erfundenen Zahlen)
    """
    # 1. Netto-Volumen (Delta)
    net_volume = buf["vol_buy"] - buf["vol_sell"]
    
    # 2. Volatilität: ((high - low) / open) * 100
    if buf["open"] and buf["open"] > 0:
        price_range = buf["high"] - buf["low"]
        volatility = (price_range / buf["open"]) * 100
    else:
        volatility = 0.0
    
    # 3. Durchschnittliche Trade-Größe
    total_trades = buf["buys"] + buf["sells"]
    if total_trades > 0:
        avg_trade_size = buf["vol"] / total_trades
    else:
        avg_trade_size = 0.0
    
    # 4. Whale-Metriken (bereits im Buffer gesammelt)
    whale_buy_vol = buf["whale_buy_vol"]
    whale_sell_vol = buf["whale_sell_vol"]
    num_whale_buys = buf["whale_buys"]
    num_whale_sells = buf["whale_sells"]
    
    return {
        "net_volume_sol": net_volume,
        "volatility_pct": volatility,
        "avg_trade_size_sol": avg_trade_size,
        "whale_buy_volume_sol": whale_buy_vol,
        "whale_sell_volume_sol": whale_sell_vol,
        "num_whale_buys": num_whale_buys,
        "num_whale_sells": num_whale_sells
    }
```

### 4.2 check_lifecycle_and_flush() erweitern
**Datei:** `tracker/main.py` (Zeile 778-791)

**Aktuell:**
```python
if now_ts >= entry["next_flush"]:
    if buf["vol"] > 0:
        is_koth = buf["mcap"] > 30000
        batch_data.append((
            mint, now_berlin, entry["meta"]["phase_id"],
            buf["open"], buf["high"], buf["low"], buf["close"], buf["mcap"],
            current_bonding_pct, buf["v_sol"], is_koth,
            buf["vol"], buf["vol_buy"], buf["vol_sell"],
            buf["buys"], buf["sells"], len(buf["wallets"]), buf["micro_trades"],
            0, buf["max_buy"], buf["max_sell"]
        ))
```

**Neu:**
```python
if now_ts >= entry["next_flush"]:
    if buf["vol"] > 0:
        is_koth = buf["mcap"] > 30000
        
        # NEU: Erweiterte Metriken berechnen
        advanced_metrics = self.calculate_advanced_metrics(buf)
        
        batch_data.append((
            mint, now_berlin, entry["meta"]["phase_id"],
            buf["open"], buf["high"], buf["low"], buf["close"], buf["mcap"],
            current_bonding_pct, buf["v_sol"], is_koth,
            buf["vol"], buf["vol_buy"], buf["vol_sell"],
            buf["buys"], buf["sells"], len(buf["wallets"]), buf["micro_trades"],
            0, buf["max_buy"], buf["max_sell"],
            # NEU: Erweiterte Metriken
            advanced_metrics["net_volume_sol"],
            advanced_metrics["volatility_pct"],
            advanced_metrics["avg_trade_size_sol"],
            advanced_metrics["whale_buy_volume_sol"],
            advanced_metrics["whale_sell_volume_sol"],
            advanced_metrics["num_whale_buys"],
            advanced_metrics["num_whale_sells"]
        ))
```

---

## 📝 Schritt 5: SQL INSERT-Statement erweitern

### 5.1 INSERT-Statement anpassen
**Datei:** `tracker/main.py` (Zeile 794-802)

**Aktuell:**
```python
sql = """
    INSERT INTO coin_metrics (
        mint, timestamp, phase_id_at_time,
        price_open, price_high, price_low, price_close, market_cap_close,
        bonding_curve_pct, virtual_sol_reserves, is_koth,
        volume_sol, buy_volume_sol, sell_volume_sol,
        num_buys, num_sells, unique_wallets, num_micro_trades,
        dev_sold_amount, max_single_buy_sol, max_single_sell_sol
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21)
"""
```

**Neu:**
```python
sql = """
    INSERT INTO coin_metrics (
        mint, timestamp, phase_id_at_time,
        price_open, price_high, price_low, price_close, market_cap_close,
        bonding_curve_pct, virtual_sol_reserves, is_koth,
        volume_sol, buy_volume_sol, sell_volume_sol,
        num_buys, num_sells, unique_wallets, num_micro_trades,
        dev_sold_amount, max_single_buy_sol, max_single_sell_sol,
        -- NEU: Erweiterte Metriken
        net_volume_sol, volatility_pct, avg_trade_size_sol,
        whale_buy_volume_sol, whale_sell_volume_sol,
        num_whale_buys, num_whale_sells
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28)
"""
```

**Wichtig:** Die Anzahl der Platzhalter ändert sich von `$21` auf `$28` (7 neue Spalten)

---

## 📝 Schritt 6: schema.sql aktualisieren

### 6.1 schema.sql erweitern
**Datei:** `sql/schema.sql`

Die neuen Spalten zur CREATE TABLE Statement hinzufügen (nach Zeile 36):

```sql
-- 6. ERWEITERTE METRIKEN (Whale & Volatilität)
net_volume_sol NUMERIC(24, 9) DEFAULT 0,           -- Delta: buy_vol - sell_vol
volatility_pct NUMERIC(10, 4) DEFAULT 0,           -- ((high - low) / open) * 100
avg_trade_size_sol NUMERIC(24, 9) DEFAULT 0,      -- volume / (num_buys + num_sells)
whale_buy_volume_sol NUMERIC(24, 9) DEFAULT 0,    -- Volumen von Trades >= 1 SOL (Buy)
whale_sell_volume_sol NUMERIC(24, 9) DEFAULT 0,    -- Volumen von Trades >= 1 SOL (Sell)
num_whale_buys INTEGER DEFAULT 0,                  -- Anzahl Whale-Buys
num_whale_sells INTEGER DEFAULT 0                  -- Anzahl Whale-Sells
```

---

## 📝 Schritt 7: Environment Variable hinzufügen

### 7.1 docker-compose.yaml erweitern
**Datei:** `docker-compose.yaml`

```yaml
environment:
  # ... bestehende ENV-Vars ...
  WHALE_THRESHOLD_SOL: ${WHALE_THRESHOLD_SOL:-1.0}
```

### 7.2 README.md aktualisieren
**Datei:** `README.md`

Neue Environment Variable dokumentieren:
- `WHALE_THRESHOLD_SOL`: Schwellenwert für Whale-Trades (Standard: 1.0 SOL)

---

## 📝 Schritt 8: Testing & Validierung

### 8.1 Test-Checkliste

- [ ] **Schema-Migration:** Neue Spalten werden korrekt erstellt
- [ ] **Buffer-Erweiterung:** Whale-Trades werden korrekt getrackt
- [ ] **Berechnung:** Alle Metriken werden korrekt berechnet
  - [ ] `net_volume_sol` = `buy_volume_sol - sell_volume_sol`
  - [ ] `volatility_pct` = `((high - low) / open) * 100` (wenn open > 0)
  - [ ] `avg_trade_size_sol` = `volume_sol / (num_buys + num_sells)` (wenn total_trades > 0)
  - [ ] Whale-Metriken nur für Trades >= `WHALE_THRESHOLD_SOL`
- [ ] **SQL-Insert:** Alle 28 Werte werden korrekt eingefügt
- [ ] **Backward-Kompatibilität:** Bestehende Daten bleiben unverändert
- [ ] **Edge Cases:** 
  - [ ] Keine Trades → alle Werte = 0
  - [ ] `price_open = 0` → `volatility_pct = 0`
  - [ ] `total_trades = 0` → `avg_trade_size_sol = 0`

### 8.2 Manuelle Tests

1. **Test 1: Normale Trades**
   ```sql
   -- Prüfe ob neue Spalten vorhanden sind
   SELECT net_volume_sol, volatility_pct, avg_trade_size_sol,
          whale_buy_volume_sol, num_whale_buys
   FROM coin_metrics
   ORDER BY timestamp DESC
   LIMIT 10;
   ```

2. **Test 2: Whale-Trades**
   - Aktiviere einen Coin mit großen Trades (>1 SOL)
   - Prüfe ob `whale_buy_volume_sol` und `num_whale_buys` korrekt sind

3. **Test 3: Volatilität**
   - Prüfe ob `volatility_pct` korrekt berechnet wird
   - Formel: `((high - low) / open) * 100`

4. **Test 4: Netto-Volumen**
   - Prüfe ob `net_volume_sol = buy_volume_sol - sell_volume_sol`

---

## 📝 Schritt 9: Dokumentation aktualisieren

### 9.1 Info-Seite erweitern
**Datei:** `ui/app.py`

Neue Metriken in der Info-Seite dokumentieren:
- Netto-Volumen (Delta)
- Volatilität
- Durchschnittliche Trade-Größe
- Whale-Tracking

### 9.2 README.md erweitern
**Datei:** `README.md`

Neue Metriken und deren Bedeutung dokumentieren.

---

## 🔄 Implementierungs-Reihenfolge

1. ✅ **Schritt 1:** Datenbank-Schema erweitern (SQL + db_migration.py)
2. ✅ **Schritt 2:** Buffer-Struktur erweitern
3. ✅ **Schritt 3:** Trade-Verarbeitung erweitern (Whale-Tracking)
4. ✅ **Schritt 4:** Metriken-Berechnung implementieren
5. ✅ **Schritt 5:** SQL INSERT-Statement anpassen
6. ✅ **Schritt 6:** schema.sql aktualisieren
7. ✅ **Schritt 7:** Environment Variable hinzufügen
8. ✅ **Schritt 8:** Testing & Validierung
9. ✅ **Schritt 9:** Dokumentation aktualisieren

---

## ⚠️ Wichtige Hinweise

### Keine erfundenen Zahlen
- ✅ Alle Werte basieren auf echten Trade-Daten aus dem Buffer
- ✅ Keine Default-Werte außer 0 (wenn keine Daten vorhanden)
- ✅ Edge Cases werden korrekt behandelt (Division durch 0, etc.)

### Datenintegrität
- ✅ Bestehende Daten bleiben unverändert (DEFAULT 0 für neue Spalten)
- ✅ Migration ist idempotent (kann mehrfach ausgeführt werden)
- ✅ Keine Datenverluste bei Update

### Performance
- ✅ Whale-Tracking erfolgt während der Trade-Verarbeitung (kein zusätzlicher Loop)
- ✅ Berechnungen sind O(1) (nur einfache Arithmetik)
- ✅ Keine zusätzlichen DB-Queries nötig

---

## 📊 Erwartete Ergebnisse

Nach der Implementierung sollten folgende Metriken verfügbar sein:

| Metrik | Beschreibung | Beispiel |
|--------|--------------|----------|
| `net_volume_sol` | Kaufdruck (positiv) oder Verkaufsdruck (negativ) | +5.2 SOL |
| `volatility_pct` | Relative Preis-Schwankung | 12.5% |
| `avg_trade_size_sol` | Durchschnittliche Trade-Größe | 0.15 SOL |
| `whale_buy_volume_sol` | Volumen von großen Buy-Trades | 10.5 SOL |
| `whale_sell_volume_sol` | Volumen von großen Sell-Trades | 3.2 SOL |
| `num_whale_buys` | Anzahl großer Buy-Trades | 5 |
| `num_whale_sells` | Anzahl großer Sell-Trades | 2 |

---

## ✅ Checkliste vor Deployment

- [ ] Alle SQL-Migrationen getestet
- [ ] Python-Code kompiliert ohne Fehler
- [ ] Alle Edge Cases behandelt
- [ ] Backward-Kompatibilität sichergestellt
- [ ] Dokumentation aktualisiert
- [ ] Environment Variables dokumentiert
- [ ] Test-Szenarien durchgeführt
- [ ] Code-Review durchgeführt

