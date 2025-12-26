# SQL Skripte für Pump Metric

## ensure_streams.sql

Dieses Skript stellt sicher, dass **keine Lücken** zwischen `discovered_coins` und `coin_streams` entstehen.

### Funktionen:

1. **`ensure_coin_stream()`** - Trigger-Funktion
   - Wird automatisch bei jedem INSERT in `discovered_coins` ausgelöst
   - Erstellt sofort einen Eintrag in `coin_streams`
   - Verhindert Lücken zu 100%

2. **`repair_missing_streams()`** - Reparatur-Funktion
   - Findet alle Coins in `discovered_coins` ohne Stream
   - Erstellt fehlende Streams nachträglich
   - Kann manuell aufgerufen werden: `SELECT repair_missing_streams()`

3. **`check_stream_gaps()`** - Monitoring-Funktion
   - Prüft auf Lücken zwischen den Tabellen
   - Gibt Report zurück mit Anzahl und Details
   - Kann regelmäßig aufgerufen werden: `SELECT * FROM check_stream_gaps()`

### Installation:

```sql
-- Führe das Skript aus:
\i ensure_streams.sql

-- Oder direkt in der Datenbank:
psql -d crypto -f ensure_streams.sql
```

### Verwendung:

**Automatisch:**
- Der Trigger läuft automatisch bei jedem neuen Coin
- Keine manuelle Aktion erforderlich

**Manuell reparieren:**
```sql
SELECT repair_missing_streams();
```

**Lücken prüfen:**
```sql
SELECT * FROM check_stream_gaps();
```

### Sicherheit:

- ✅ **ON CONFLICT DO NOTHING** verhindert Fehler bei Duplikaten
- ✅ **Trigger läuft atomar** - keine Lücken möglich
- ✅ **Automatische Reparatur** im Tracker (alle 60s)
- ✅ **Monitoring** erkennt Lücken sofort


