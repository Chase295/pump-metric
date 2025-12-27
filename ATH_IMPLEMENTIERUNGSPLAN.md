# 🎯 ATH (All-Time High) Tracking - Implementierungsplan

## 📋 Übersicht

Dieser Plan beschreibt die schrittweise Implementierung von ATH-Tracking im `pump-metric` System. Das ATH wird **hybrid** getrackt:
- **RAM (ath_cache)**: Für Millisekunden-Entscheidungen (sofort verfügbar)
- **Datenbank (coin_streams)**: Für Persistenz (überlebt Neustarts)

---

## 🗂️ Schritt 1: Datenbank-Schema erweitern

### 1.1 SQL-Migration erstellen

**Datei:** `sql/add_ath_tracking.sql`

```sql
-- Füge ATH-Spalten zur coin_streams Tabelle hinzu
ALTER TABLE coin_streams 
ADD COLUMN IF NOT EXISTS ath_price_sol NUMERIC DEFAULT 0,
ADD COLUMN IF NOT EXISTS ath_timestamp TIMESTAMPTZ;

-- Index für schnelle ATH-Abfragen (optional, aber empfohlen)
CREATE INDEX IF NOT EXISTS idx_streams_ath_price 
ON coin_streams(ath_price_sol DESC) 
WHERE is_active = TRUE;

-- Kommentare für Dokumentation
COMMENT ON COLUMN coin_streams.ath_price_sol IS 'All-Time High Preis in SOL (wird live getrackt)';
COMMENT ON COLUMN coin_streams.ath_timestamp IS 'Timestamp des letzten ATH-Updates';
```

### 1.2 db_migration.py erweitern

**Datei:** `tracker/db_migration.py`

**Änderung:** Füge ATH-Spalten-Prüfung hinzu (nach Zeile 163, wo `coin_streams` geprüft wird):

```python
# Prüfe coin_streams Tabelle (wird von pump-discover erstellt, aber prüfen wir trotzdem)
streams_exists = await conn.fetchval("""
    SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'coin_streams'
    )
""")

if not streams_exists:
    print("⚠️  coin_streams Tabelle nicht gefunden - wird von pump-discover erstellt", flush=True)
else:
    print("✅ coin_streams Tabelle vorhanden", flush=True)
    
    # NEU: Prüfe ATH-Spalten
    ath_columns = await conn.fetch("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'coin_streams' 
        AND column_name IN ('ath_price_sol', 'ath_timestamp')
    """)
    existing_ath_columns = {row['column_name'] for row in ath_columns}
    
    if 'ath_price_sol' not in existing_ath_columns:
        print("📊 Füge ath_price_sol Spalte hinzu...", flush=True)
        await conn.execute("ALTER TABLE coin_streams ADD COLUMN ath_price_sol NUMERIC DEFAULT 0;")
        print("✅ ath_price_sol hinzugefügt", flush=True)
    
    if 'ath_timestamp' not in existing_ath_columns:
        print("📊 Füge ath_timestamp Spalte hinzu...", flush=True)
        await conn.execute("ALTER TABLE coin_streams ADD COLUMN ath_timestamp TIMESTAMPTZ;")
        print("✅ ath_timestamp hinzugefügt", flush=True)
```

---

## 🐍 Schritt 2: Python-Code Anpassungen

### 2.1 Initialisierung: ATH-Cache beim Start laden

**Datei:** `tracker/main.py`

**Änderung 1:** In `__init__` Methode (nach Zeile 336):

```python
class Tracker:
    def __init__(self):
        self.pool = None
        self.phases_config = {}
        self.watchlist = {}
        self.subscribed_mints = set()
        self.sorted_phase_ids = []
        self.trade_buffer = {}
        self.last_buffer_cleanup = time.time()
        self.early_subscribed_mints = set()
        
        # NEU: ATH-Tracking
        self.ath_cache = {}  # {mint: ath_price} - RAM-Cache für sofortige Verfügbarkeit
        self.dirty_aths = set()  # {mint} - Set von Coins, deren ATH in DB geschrieben werden muss
        self.last_ath_flush = time.time()  # Timestamp des letzten ATH-Flush
```

**Änderung 2:** In `get_active_streams()` Methode (Zeile 385-405):

```python
async def get_active_streams(self):
    try:
        with db_query_duration.time():
            # Zuerst: Repariere fehlende Streams (sicherheitshalber)
            try:
                await self.pool.execute("SELECT repair_missing_streams()")
            except Exception as e:
                # Funktion existiert möglicherweise noch nicht - ignorieren
                pass
            
            # Dann: Hole aktive Streams (MIT ATH)
            sql = """
                SELECT cs.token_address, cs.current_phase_id, dc.token_created_at, 
                       cs.started_at, dc.trader_public_key,
                       cs.ath_price_sol  -- NEU: ATH mit abfragen
                FROM coin_streams cs
                JOIN discovered_coins dc ON cs.token_address = dc.token_address
                WHERE cs.is_active = TRUE
            """
            rows = await self.pool.fetch(sql)
            results = {}
            for row in rows:
                mint = row["token_address"]
                created_at = row["token_created_at"]
                started_at = row["started_at"]
                if not created_at: created_at = datetime.now(timezone.utc)
                if created_at.tzinfo is None: created_at = created_at.replace(tzinfo=timezone.utc)
                if started_at and started_at.tzinfo is None: started_at = started_at.replace(tzinfo=timezone.utc)
                
                # NEU: ATH aus DB laden und in Cache speichern
                db_ath = row.get("ath_price_sol")
                if db_ath is None:
                    db_ath = 0.0
                else:
                    db_ath = float(db_ath)
                
                # Cache füllen (wichtig für sofortige Verfügbarkeit)
                if mint not in self.ath_cache:
                    self.ath_cache[mint] = db_ath
                elif self.ath_cache[mint] < db_ath:
                    # DB hat höheren Wert - aktualisiere Cache
                    self.ath_cache[mint] = db_ath
                
                results[mint] = {
                    "phase_id": row["current_phase_id"],
                    "created_at": created_at,
                    "started_at": started_at or created_at,
                    "creator_address": row.get("trader_public_key")
                }
            
            # ... Rest der Methode bleibt gleich ...
```

### 2.2 Trade-Verarbeitung: ATH-Check

**Datei:** `tracker/main.py`

**Änderung:** In `process_trade()` Methode (nach Zeile 920, wo `price` berechnet wird):

```python
def process_trade(self, data):
    """Verarbeitet einen einzelnen Trade (direkt oder aus Buffer)"""
    mint = data["mint"]
    if mint not in self.watchlist: return
    entry = self.watchlist[mint]
    buf = entry["buffer"]
    try:
        sol = float(data["solAmount"])
        price = float(data["vSolInBondingCurve"]) / float(data["vTokensInBondingCurve"])
        is_buy = data["txType"] == "buy"
        trader_key = data.get("traderPublicKey", "")
    except: return
    
    # --- NEUER ATH CHECK START ---
    # 1. Hole aktuelles ATH aus RAM (oder 0.0 wenn nicht vorhanden)
    known_ath = self.ath_cache.get(mint, 0.0)
    
    # 2. Ist der aktuelle Preis höher?
    if price > known_ath:
        # Update im RAM (Sofort verfügbar für Logik)
        self.ath_cache[mint] = price
        
        # Markiere für DB-Update (nicht sofort schreiben, das bremst!)
        self.dirty_aths.add(mint)
        
        # Optional: Logging für Debugging (nur bei signifikanten Änderungen)
        if price > known_ath * 1.1:  # Nur loggen wenn >10% höher
            print(f"📈 ATH Update: {mint[:8]}... {known_ath:.6f} -> {price:.6f} SOL (+{((price/known_ath-1)*100):.1f}%)", flush=True)
    # --- NEUER ATH CHECK ENDE ---
    
    # Rest der Methode bleibt gleich (OHLC, Volume, etc.)
    if buf["open"] is None: buf["open"] = price
    buf["close"] = price
    buf["high"] = max(buf["high"], price)
    buf["low"] = min(buf["low"], price)
    # ... Rest bleibt unverändert ...
```

### 2.3 Batch-Update: ATH in DB speichern

**Datei:** `tracker/main.py`

**Änderung 1:** Neue Methode `flush_ath_updates()` hinzufügen (nach `calculate_advanced_metrics()`, ca. Zeile 1007):

```python
async def flush_ath_updates(self):
    """
    Schreibt geänderte ATH-Werte in die Datenbank (Batch-Update)
    Wird periodisch aufgerufen, um DB-Last zu minimieren
    """
    if not self.dirty_aths:
        return  # Keine Änderungen
    
    if not self.pool or not tracker_status["db_connected"]:
        # DB nicht verbunden - behalte dirty_aths für später
        return
    
    # Liste für Batch-Update vorbereiten
    updates = []
    for mint in self.dirty_aths:
        new_ath = self.ath_cache.get(mint, 0.0)
        if new_ath > 0:  # Nur positive Werte speichern
            updates.append((new_ath, mint))
    
    if not updates:
        self.dirty_aths.clear()
        return
    
    try:
        # SQL für Massen-Update (extrem effizient - nur ein DB-Call für alle Updates)
        query = """
            UPDATE coin_streams 
            SET ath_price_sol = $1, ath_timestamp = NOW()
            WHERE token_address = $2
        """
        
        async with self.pool.acquire() as conn:
            # Führt alle Updates in einem Rutsch aus (executemany ist sehr schnell)
            await conn.executemany(query, updates)
        
        # Nach erfolgreichem Schreiben: Liste leeren
        updated_count = len(updates)
        self.dirty_aths.clear()
        self.last_ath_flush = time.time()
        
        # Optional: Logging (nur bei vielen Updates)
        if updated_count > 10:
            print(f"💾 ATH-Update: {updated_count} Coins in DB gespeichert", flush=True)
        
    except Exception as e:
        print(f"❌ Fehler beim ATH-Update: {e}", flush=True)
        # Fehler ignorieren - dirty_aths bleibt gesetzt, wird beim nächsten Mal erneut versucht
        db_errors.labels(type="ath_update").inc()
```

**Änderung 2:** `flush_ath_updates()` in Main-Loop aufrufen

**Datei:** `tracker/main.py`

**Änderung:** In `run()` Methode, im Main-Loop (nach `check_lifecycle_and_flush()`, ca. Zeile 784):

```python
# Buffer-Cleanup alle 10 Sekunden
if now_ts - self.last_buffer_cleanup > 10:
    removed = self.cleanup_old_trades_from_buffer(now_ts)
    if removed > 0:
        print(f"🧹 Buffer-Cleanup: {removed} alte Trades entfernt", flush=True)
    self.last_buffer_cleanup = now_ts

await self.check_lifecycle_and_flush(now_ts)

# NEU: ATH-Updates alle 5 Sekunden (oder nach jedem Flush)
ath_flush_interval = 5.0  # Sekunden
if now_ts - self.last_ath_flush > ath_flush_interval:
    await self.flush_ath_updates()
```

**Alternative:** ATH-Flush direkt nach `check_lifecycle_and_flush()` (empfohlen):

```python
await self.check_lifecycle_and_flush(now_ts)

# NEU: ATH-Updates nach jedem Metric-Flush (oder alle 5 Sekunden)
if now_ts - self.last_ath_flush > 5.0:
    await self.flush_ath_updates()
```

### 2.4 ATH-Cache beim Coin-Entfernen aufräumen

**Datei:** `tracker/main.py`

**Änderung:** In `stop_tracking()` Methode (nach Zeile 468):

```python
async def stop_tracking(self, mint, is_graduation=False):
    try:
        # ... bestehender Code ...
    finally:
        if mint in self.watchlist: del self.watchlist[mint]
        if mint in self.subscribed_mints: self.subscribed_mints.remove(mint)
        
        # NEU: ATH-Cache aufräumen (optional - kann auch bleiben für historische Daten)
        # if mint in self.ath_cache: del self.ath_cache[mint]
        if mint in self.dirty_aths: self.dirty_aths.remove(mint)
        
        coins_tracked.set(len(self.watchlist))
```

---

## 🔧 Schritt 3: Konfiguration & Performance

### 3.1 ATH-Flush-Intervall konfigurierbar machen

**Datei:** `tracker/main.py`

**Änderung:** In Konfiguration (nach Zeile 30):

```python
ATH_FLUSH_INTERVAL = int(os.getenv("ATH_FLUSH_INTERVAL", "5"))  # Sekunden zwischen ATH-Flushes
```

**Änderung:** In `load_config_from_file()` (nach Zeile 85):

```python
elif key == "ATH_FLUSH_INTERVAL" and value.isdigit():
    ATH_FLUSH_INTERVAL = int(value)
```

**Änderung:** In Main-Loop verwenden:

```python
if now_ts - self.last_ath_flush > ATH_FLUSH_INTERVAL:
    await self.flush_ath_updates()
```

### 3.2 Prometheus-Metriken für ATH-Tracking

**Datei:** `tracker/main.py`

**Änderung:** Nach Zeile 117 (Prometheus Metrics):

```python
ath_updates_total = PromCounter("tracker_ath_updates_total", "Anzahl ATH-Updates in DB")
ath_cache_size = Gauge("tracker_ath_cache_size", "Anzahl Coins im ATH-Cache")
```

**Änderung:** In `flush_ath_updates()`:

```python
ath_updates_total.inc(updated_count)
ath_cache_size.set(len(self.ath_cache))
```

---

## ✅ Schritt 4: Testing & Validierung

### 4.1 Test-Checkliste

- [ ] **Schema-Migration**: SQL-Script ausführen, Spalten prüfen
- [ ] **Startup**: ATH-Cache wird beim Start geladen (Logs prüfen)
- [ ] **Trade-Verarbeitung**: Neues ATH wird erkannt und im Cache gespeichert
- [ ] **DB-Update**: ATH wird periodisch in DB geschrieben
- [ ] **Neustart**: ATH-Werte überleben Neustart (aus DB geladen)
- [ ] **Performance**: Keine spürbare Verlangsamung bei Trade-Verarbeitung

### 4.2 SQL-Queries zum Testen

```sql
-- Prüfe ATH-Spalten
SELECT token_address, ath_price_sol, ath_timestamp 
FROM coin_streams 
WHERE is_active = TRUE 
ORDER BY ath_price_sol DESC 
LIMIT 10;

-- Prüfe ATH-Updates (sollte regelmäßig aktualisiert werden)
SELECT COUNT(*) as coins_with_ath, 
       MAX(ath_timestamp) as last_update
FROM coin_streams 
WHERE is_active = TRUE AND ath_price_sol > 0;
```

---

## 📊 Schritt 5: UI-Integration (Optional)

### 5.1 ATH in Dashboard anzeigen

**Datei:** `ui/app.py`

**Änderung:** In Dashboard-Tab, ATH-Spalte hinzufügen (optional, für spätere Erweiterung)

---

## 🚀 Deployment-Reihenfolge

1. **SQL-Migration ausführen** (`sql/add_ath_tracking.sql`)
2. **Code-Änderungen committen**
3. **Docker-Container neu bauen**
4. **Service neu starten**
5. **Logs prüfen** (ATH-Cache wird geladen)
6. **Trades beobachten** (ATH-Updates sollten in Logs erscheinen)
7. **DB prüfen** (ATH-Werte sollten aktualisiert werden)

---

## ⚠️ Wichtige Hinweise

### Performance
- **ATH-Check ist O(1)** - nur ein Dictionary-Lookup
- **Batch-Update** minimiert DB-Last (nur geänderte Werte)
- **Kein Blocking** - ATH-Update läuft asynchron

### Datenintegrität
- **RAM ist Single-Source-of-Truth** während Laufzeit
- **DB ist Backup** für Persistenz
- **Bei Neustart**: DB-Werte werden in RAM geladen

### Edge Cases
- **Coin wird entfernt**: ATH bleibt in DB (für historische Analyse)
- **DB-Fehler**: `dirty_aths` bleibt gesetzt, wird beim nächsten Mal erneut versucht
- **Negative Preise**: Werden ignoriert (nur positive ATH-Werte)

---

## 📝 Zusammenfassung

**Was wird implementiert:**
1. ✅ Datenbank-Schema: `ath_price_sol`, `ath_timestamp` in `coin_streams`
2. ✅ RAM-Cache: `ath_cache` für sofortige Verfügbarkeit
3. ✅ Trade-Check: ATH wird bei jedem Trade geprüft
4. ✅ Batch-Update: Periodisches Schreiben in DB (alle 5 Sekunden)
5. ✅ Startup-Loading: ATH-Werte werden beim Start aus DB geladen

**Vorteile:**
- ⚡ **Blitzschnell**: RAM-Cache für Millisekunden-Entscheidungen
- 💾 **Persistent**: Überlebt Neustarts
- 🚀 **Effizient**: Batch-Updates minimieren DB-Last
- 🔄 **Automatisch**: Keine manuelle Intervention nötig

---

**Erstellt:** 2025-01-26  
**Version:** 1.0  
**Status:** Bereit zur Implementierung

