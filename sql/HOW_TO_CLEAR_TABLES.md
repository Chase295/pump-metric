# Tabellen leeren - Anleitung

## 🗑️ Wie lösche ich alle Daten aus den Tabellen?

### Option 1: Mit psql (Kommandozeile)

```bash
# Verbinde dich mit der Datenbank
psql -h DEINE_HOST -U DEIN_USER -d crypto

# Dann führe die Queries aus:
```

```sql
BEGIN;
TRUNCATE TABLE coin_metrics CASCADE;
TRUNCATE TABLE coin_streams CASCADE;
TRUNCATE TABLE discovered_coins CASCADE;
COMMIT;
```

### Option 2: SQL-Datei ausführen

```bash
# Von der Kommandozeile
psql -h DEINE_HOST -U DEIN_USER -d crypto -f sql/clear_tables.sql

# Oder mit vollständigem Pfad
psql -h 100.118.155.75 -U postgres -d crypto -f sql/clear_tables.sql
```

### Option 3: Mit pgAdmin (GUI)

1. Öffne **pgAdmin**
2. Verbinde dich mit deiner Datenbank
3. Rechtsklick auf die Datenbank → **Query Tool**
4. Öffne die Datei `sql/clear_tables.sql`
5. Führe die Queries aus (F5 oder Play-Button)

### Option 4: Mit DBeaver (GUI)

1. Öffne **DBeaver**
2. Verbinde dich mit deiner Datenbank
3. Öffne ein **SQL Editor**
4. Kopiere die Queries aus `sql/clear_tables.sql`
5. Führe sie aus (Strg+Enter)

### Option 5: Direkt in der Datenbank

```sql
-- Kopiere diese Queries und führe sie in deinem SQL-Client aus:

BEGIN;

TRUNCATE TABLE coin_metrics CASCADE;
TRUNCATE TABLE coin_streams CASCADE;
TRUNCATE TABLE discovered_coins CASCADE;

COMMIT;
```

## ⚠️ Wichtige Hinweise

1. **TRUNCATE vs DELETE**:
   - `TRUNCATE` ist schneller und setzt Auto-Increment zurück
   - `DELETE` ist langsamer, aber funktioniert immer

2. **CASCADE**:
   - `CASCADE` löscht auch abhängige Daten
   - Wichtig bei Foreign Key Constraints

3. **ref_coin_phases**:
   - Diese Tabelle wird **NICHT** geleert
   - Enthält Referenz-Daten die erhalten bleiben sollten

4. **Backup**:
   - Erstelle ein Backup vor dem Löschen:
   ```bash
   pg_dump -h DEINE_HOST -U DEIN_USER -d crypto > backup.sql
   ```

## ✅ Prüfen ob Tabellen leer sind

```sql
SELECT 
    'coin_metrics' as tabelle, COUNT(*) as anzahl FROM coin_metrics
UNION ALL
SELECT 
    'coin_streams', COUNT(*) FROM coin_streams
UNION ALL
SELECT 
    'discovered_coins', COUNT(*) FROM discovered_coins;
```

**Erwartete Ausgabe** (wenn leer):
```
tabelle         | anzahl
----------------+--------
coin_metrics    |      0
coin_streams    |      0
discovered_coins|      0
```

## 🔄 Nur coin_metrics leeren (Coins bleiben erhalten)

Wenn du nur die Metriken löschen willst, aber die Coins behalten:

```sql
TRUNCATE TABLE coin_metrics;
```

## 📝 Beispiel mit deiner Datenbank

Basierend auf deiner `docker-compose.yaml`:

```bash
# Verbindung zur Datenbank
psql -h 100.118.155.75 -U postgres -d crypto

# Dann in psql:
\i sql/clear_tables.sql
```

Oder direkt:

```bash
psql -h 100.118.155.75 -U postgres -d crypto -c "TRUNCATE TABLE coin_metrics, coin_streams, discovered_coins CASCADE;"
```

