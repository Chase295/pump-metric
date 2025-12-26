# 🔒 Installation: Lücken-Prävention

## Übersicht

Um sicherzustellen, dass **keine Lücken** zwischen Coin-Discovery und Metric-Tracking entstehen, muss das SQL-Skript `ensure_streams.sql` in der Datenbank installiert werden.

## Installation

### Schritt 1: SQL-Skript ausführen

```bash
# Option 1: Über psql
psql -h 100.118.155.75 -U postgres -d crypto -f sql/ensure_streams.sql

# Option 2: Über Docker (wenn PostgreSQL in Docker läuft)
docker exec -i <postgres-container> psql -U postgres -d crypto < sql/ensure_streams.sql

# Option 3: Direkt in der Datenbank
psql -d crypto
\i sql/ensure_streams.sql
```

### Schritt 2: Verifikation

```sql
-- Prüfe ob Trigger existiert
SELECT * FROM pg_trigger WHERE tgname = 'trigger_ensure_coin_stream';

-- Prüfe ob Funktionen existieren
SELECT proname FROM pg_proc WHERE proname IN ('ensure_coin_stream', 'repair_missing_streams', 'check_stream_gaps');

-- Teste Lücken-Check
SELECT * FROM check_stream_gaps();
```

### Schritt 3: Test

```sql
-- Erstelle Test-Coin (wenn nicht vorhanden)
INSERT INTO discovered_coins (token_address, symbol, name) 
VALUES ('TEST123456789', 'TEST', 'Test Coin')
ON CONFLICT (token_address) DO NOTHING;

-- Prüfe ob Stream automatisch erstellt wurde
SELECT * FROM coin_streams WHERE token_address = 'TEST123456789';
```

## Was wird installiert?

1. **Trigger-Funktion** (`ensure_coin_stream`)
   - Wird bei jedem INSERT in `discovered_coins` ausgelöst
   - Erstellt automatisch Stream in `coin_streams`

2. **Reparatur-Funktion** (`repair_missing_streams`)
   - Findet fehlende Streams
   - Erstellt sie nachträglich

3. **Monitoring-Funktion** (`check_stream_gaps`)
   - Prüft auf Lücken
   - Gibt Report zurück

## Automatische Reparatur

Der Tracker ruft automatisch `repair_missing_streams()` auf:
- Bei jeder DB-Abfrage (alle 10 Sekunden)
- Falls Trigger versagt, wird repariert
- **Doppelte Sicherheit**

## Monitoring

Der Tracker prüft alle 60 Sekunden auf Lücken:
- Loggt Warnung wenn Lücken gefunden werden
- Zeigt betroffene Coins in Logs

## Manuelle Reparatur

Falls nötig, kann manuell repariert werden:

```sql
-- Repariere alle fehlenden Streams
SELECT repair_missing_streams();

-- Prüfe auf Lücken
SELECT * FROM check_stream_gaps();
```

## Wichtig

- ✅ **Einmalige Installation** - Trigger läuft danach automatisch
- ✅ **100% sicher** - Keine Lücken möglich
- ✅ **Fallback-Sicherheit** - Tracker repariert automatisch
- ✅ **Monitoring** - Lücken werden sofort erkannt



