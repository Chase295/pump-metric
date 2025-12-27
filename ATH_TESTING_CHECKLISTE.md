# 🧪 ATH-Tracking - Testing & Validierung Checkliste

## 📋 Test-Checkliste

### ✅ Phase 1: Schema-Migration

- [ ] **SQL-Migration ausführen** (optional - wird automatisch gemacht)
  ```bash
  psql -d crypto -f sql/add_ath_tracking.sql
  ```

- [ ] **Automatische Migration prüfen**
  - Container starten: `docker compose up -d tracker`
  - Logs prüfen: `docker compose logs tracker | grep -i ath`
  - Erwartete Ausgabe:
    ```
    📊 Füge ath_price_sol Spalte zu coin_streams hinzu...
    ✅ ath_price_sol hinzugefügt
    📊 Füge ath_timestamp Spalte zu coin_streams hinzu...
    ✅ ath_timestamp hinzugefügt
    📊 Erstelle Index idx_streams_ath_price...
    ✅ ATH-Index erstellt
    ```

- [ ] **Spalten in DB prüfen**
  ```sql
  SELECT column_name, data_type, column_default
  FROM information_schema.columns 
  WHERE table_name = 'coin_streams' 
  AND column_name IN ('ath_price_sol', 'ath_timestamp');
  ```
  **Erwartet**: 2 Zeilen mit `ath_price_sol` (NUMERIC) und `ath_timestamp` (TIMESTAMPTZ)

- [ ] **Index prüfen**
  ```sql
  SELECT indexname, indexdef 
  FROM pg_indexes 
  WHERE tablename = 'coin_streams' 
  AND indexname = 'idx_streams_ath_price';
  ```
  **Erwartet**: 1 Zeile mit Index-Definition

---

### ✅ Phase 2: Startup & Initialisierung

- [ ] **ATH-Cache wird beim Start geladen**
  - Logs prüfen: `docker compose logs tracker | grep -i "get_active_streams"`
  - Erwartete Ausgabe: Keine Fehler, ATH-Werte werden aus DB geladen

- [ ] **Prometheus-Metrik `tracker_ath_cache_size` prüfen**
  ```bash
  curl http://localhost:8011/metrics | grep ath_cache_size
  ```
  **Erwartet**: `tracker_ath_cache_size <zahl>` (Anzahl Coins im Cache)

- [ ] **Health-Check prüfen**
  ```bash
  curl http://localhost:8011/health | jq .db_tables
  ```
  **Erwartet**: `coin_streams_exists: true`

---

### ✅ Phase 3: Trade-Verarbeitung

- [ ] **ATH wird bei neuem Trade geprüft**
  - Logs beobachten: `docker compose logs -f tracker`
  - Erwartete Ausgabe bei neuem ATH:
    ```
    📈 ATH Update: <mint>... <old_ath> -> <new_ath> SOL (+<pct>%)
    ```
  - **Hinweis**: Logging nur bei signifikanten Änderungen (>10%)

- [ ] **ATH-Cache wird aktualisiert**
  - Prometheus-Metrik prüfen: `curl http://localhost:8011/metrics | grep ath_cache_size`
  - **Erwartet**: Wert sollte steigen, wenn neue Coins getrackt werden

- [ ] **dirty_aths wird gefüllt**
  - **Hinweis**: Kann nicht direkt geprüft werden, aber indirekt über DB-Updates

---

### ✅ Phase 4: DB-Update (Batch-Flush)

- [ ] **ATH wird periodisch in DB geschrieben**
  - Warte 5-10 Sekunden nach neuem ATH
  - Prüfe DB:
    ```sql
    SELECT token_address, ath_price_sol, ath_timestamp 
    FROM coin_streams 
    WHERE is_active = TRUE 
      AND ath_timestamp > NOW() - INTERVAL '1 minute'
    ORDER BY ath_timestamp DESC;
    ```
  - **Erwartet**: Zeilen mit aktualisierten ATH-Werten

- [ ] **Prometheus-Metrik `tracker_ath_updates_total` prüfen**
  ```bash
  curl http://localhost:8011/metrics | grep ath_updates_total
  ```
  **Erwartet**: `tracker_ath_updates_total <zahl>` (sollte steigen)

- [ ] **Batch-Update funktioniert**
  - Mehrere Coins mit neuen ATHs
  - Warte 5 Sekunden
  - Prüfe DB: Alle sollten aktualisiert sein

---

### ✅ Phase 5: Neustart & Persistenz

- [ ] **ATH-Werte überleben Neustart**
  - Notiere ATH-Werte vor Neustart:
    ```sql
    SELECT token_address, ath_price_sol 
    FROM coin_streams 
    WHERE is_active = TRUE 
    ORDER BY ath_price_sol DESC 
    LIMIT 5;
    ```
  - Container neu starten: `docker compose restart tracker`
  - Warte 30 Sekunden
  - Prüfe erneut: ATH-Werte sollten gleich sein

- [ ] **ATH-Cache wird nach Neustart geladen**
  - Logs prüfen: `docker compose logs tracker | grep -i ath`
  - **Erwartet**: Keine Fehler, Cache wird aus DB geladen

---

### ✅ Phase 6: Performance

- [ ] **Keine spürbare Verlangsamung**
  - Trade-Verarbeitung sollte weiterhin schnell sein
  - Prüfe Logs: Keine Timeouts oder Verzögerungen

- [ ] **DB-Last ist minimal**
  - Prüfe DB-Query-Dauer in Prometheus:
    ```bash
    curl http://localhost:8011/metrics | grep db_query_duration
    ```
  - **Erwartet**: Keine signifikante Erhöhung

- [ ] **Batch-Updates funktionieren effizient**
  - Mehrere ATH-Updates sollten in einem DB-Call geschrieben werden
  - Prüfe Logs: `💾 ATH-Update: <anzahl> Coins in DB gespeichert`

---

### ✅ Phase 7: Edge Cases

- [ ] **Coin wird entfernt (stop_tracking)**
  - Coin sollte aus `dirty_aths` entfernt werden
  - ATH-Wert bleibt in DB (für historische Analyse)

- [ ] **DB-Fehler während Flush**
  - Simuliere DB-Fehler (z.B. DB-Verbindung trennen)
  - **Erwartet**: Fehler wird geloggt, `dirty_aths` bleibt gesetzt
  - Nach DB-Reconnect: ATH-Updates werden erneut versucht

- [ ] **Negative Preise**
  - **Erwartet**: Werden ignoriert (nur positive ATH-Werte)

- [ ] **Gleicher Preis wie ATH**
  - **Erwartet**: Kein Update (nur wenn `price > ath`)

---

### ✅ Phase 8: UI-Integration

- [ ] **ATH-Metriken werden in UI angezeigt**
  - Öffne UI: `http://localhost:8501`
  - Gehe zu Tab "📈 Metriken"
  - **Erwartet**: ATH-Tracking Sektion mit Metriken

- [ ] **Info-Seite zeigt ATH-Dokumentation**
  - Gehe zu Tab "📖 Info"
  - Scroll zu "📈 8. ATH-Tracking (All-Time High)"
  - **Erwartet**: Vollständige Dokumentation mit SQL-Beispielen

---

## 🔍 SQL-Test-Queries

### Basis-Tests

```sql
-- 1. Prüfe ob ATH-Spalten existieren
SELECT column_name, data_type, column_default
FROM information_schema.columns 
WHERE table_name = 'coin_streams' 
AND column_name IN ('ath_price_sol', 'ath_timestamp');

-- 2. Prüfe Index
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename = 'coin_streams' 
AND indexname = 'idx_streams_ath_price';

-- 3. Zeige alle aktiven Coins mit ATH
SELECT 
    token_address,
    ath_price_sol,
    ath_timestamp,
    is_active
FROM coin_streams 
WHERE is_active = TRUE
ORDER BY ath_price_sol DESC NULLS LAST
LIMIT 20;
```

### ATH-Analyse

```sql
-- 4. Top 10 Coins nach ATH
SELECT 
    token_address,
    ath_price_sol,
    ath_timestamp,
    current_phase_id
FROM coin_streams 
WHERE is_active = TRUE 
  AND ath_price_sol > 0
ORDER BY ath_price_sol DESC 
LIMIT 10;

-- 5. Coins mit ATH-Updates in den letzten 10 Minuten
SELECT 
    token_address,
    ath_price_sol,
    ath_timestamp,
    EXTRACT(EPOCH FROM (NOW() - ath_timestamp)) / 60 as minutes_ago
FROM coin_streams 
WHERE is_active = TRUE 
  AND ath_timestamp > NOW() - INTERVAL '10 minutes'
ORDER BY ath_timestamp DESC;

-- 6. ATH-Statistiken
SELECT 
    COUNT(*) as total_active_coins,
    COUNT(ath_price_sol) as coins_with_ath,
    MAX(ath_price_sol) as highest_ath,
    AVG(ath_price_sol) as avg_ath,
    MIN(ath_timestamp) as oldest_ath_update,
    MAX(ath_timestamp) as newest_ath_update
FROM coin_streams 
WHERE is_active = TRUE;

-- 7. Coins ohne ATH (sollten 0 sein nach einiger Zeit)
SELECT 
    token_address,
    current_phase_id,
    started_at
FROM coin_streams 
WHERE is_active = TRUE 
  AND (ath_price_sol IS NULL OR ath_price_sol = 0)
ORDER BY started_at DESC;
```

### Performance-Tests

```sql
-- 8. Prüfe Index-Nutzung (EXPLAIN ANALYZE)
EXPLAIN ANALYZE
SELECT token_address, ath_price_sol 
FROM coin_streams 
WHERE is_active = TRUE 
  AND ath_price_sol > 0
ORDER BY ath_price_sol DESC 
LIMIT 10;

-- Erwartet: Index Scan auf idx_streams_ath_price

-- 9. Prüfe Update-Performance
BEGIN;
UPDATE coin_streams 
SET ath_price_sol = 0.001, ath_timestamp = NOW()
WHERE token_address = '<test_mint>';
-- Prüfe Query-Dauer
ROLLBACK;
```

### Validierung

```sql
-- 10. Prüfe Konsistenz: ATH sollte >= aktueller Preis sein
SELECT 
    cs.token_address,
    cs.ath_price_sol,
    cm.price_close as current_price,
    cm.timestamp as metric_timestamp
FROM coin_streams cs
JOIN coin_metrics cm ON cs.token_address = cm.mint
WHERE cs.is_active = TRUE
  AND cs.ath_price_sol > 0
  AND cm.timestamp > NOW() - INTERVAL '1 hour'
  AND cm.price_close > cs.ath_price_sol  -- Sollte keine Zeilen geben!
ORDER BY cm.timestamp DESC
LIMIT 20;

-- 11. Prüfe ATH-Timestamp ist aktuell
SELECT 
    token_address,
    ath_price_sol,
    ath_timestamp,
    EXTRACT(EPOCH FROM (NOW() - ath_timestamp)) / 60 as minutes_since_update
FROM coin_streams 
WHERE is_active = TRUE 
  AND ath_timestamp IS NOT NULL
  AND ath_timestamp < NOW() - INTERVAL '1 hour'  -- Älter als 1 Stunde
ORDER BY ath_timestamp ASC;

-- 12. Vergleich: ATH vs. coin_metrics price_high
SELECT 
    cs.token_address,
    cs.ath_price_sol as stream_ath,
    MAX(cm.price_high) as metrics_max_high,
    cs.ath_price_sol - MAX(cm.price_high) as difference
FROM coin_streams cs
LEFT JOIN coin_metrics cm ON cs.token_address = cm.mint
WHERE cs.is_active = TRUE
  AND cs.ath_price_sol > 0
GROUP BY cs.token_address, cs.ath_price_sol
HAVING cs.ath_price_sol > MAX(cm.price_high) * 1.1  -- ATH sollte nicht viel höher sein
ORDER BY difference DESC
LIMIT 10;
```

---

## 🐛 Troubleshooting

### Problem: ATH wird nicht aktualisiert

**Prüfungen**:
1. Prüfe ob Trades ankommen: `curl http://localhost:8011/health | jq .total_trades`
2. Prüfe Logs auf ATH-Updates: `docker compose logs tracker | grep -i "ATH"`
3. Prüfe DB: `SELECT * FROM coin_streams WHERE is_active = TRUE LIMIT 5;`
4. Prüfe Prometheus-Metriken: `curl http://localhost:8011/metrics | grep ath`

**Lösungen**:
- Prüfe ob `ATH_FLUSH_INTERVAL` korrekt gesetzt ist
- Prüfe ob DB-Verbindung funktioniert
- Prüfe ob Trades tatsächlich höhere Preise haben

### Problem: ATH-Cache ist leer

**Prüfungen**:
1. Prüfe ob Coins in `coin_streams` aktiv sind
2. Prüfe Logs beim Start: `docker compose logs tracker | grep -i "get_active_streams"`
3. Prüfe DB: `SELECT COUNT(*) FROM coin_streams WHERE is_active = TRUE;`

**Lösungen**:
- Warte bis Coins aktiviert werden
- Prüfe ob `get_active_streams()` korrekt ATH-Werte lädt

### Problem: DB-Updates fehlschlagen

**Prüfungen**:
1. Prüfe DB-Verbindung: `curl http://localhost:8011/health | jq .db_connected`
2. Prüfe Logs: `docker compose logs tracker | grep -i "ATH-Update"`
3. Prüfe DB-Berechtigungen

**Lösungen**:
- Prüfe DB-Verbindungsstring
- Prüfe DB-Berechtigungen für UPDATE auf `coin_streams`
- Prüfe ob Spalten existieren

---

## ✅ Erfolgskriterien

Die Implementierung ist erfolgreich, wenn:

1. ✅ ATH-Spalten werden automatisch erstellt
2. ✅ ATH-Werte werden beim Start geladen
3. ✅ ATH wird bei jedem Trade geprüft
4. ✅ ATH-Updates werden periodisch in DB geschrieben
5. ✅ ATH-Werte überleben Neustarts
6. ✅ Keine Performance-Probleme
7. ✅ UI zeigt ATH-Metriken
8. ✅ Alle SQL-Test-Queries funktionieren

---

**Erstellt:** 2025-01-26  
**Version:** 1.0  
**Status:** Bereit für Testing

