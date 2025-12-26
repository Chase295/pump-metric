# SQL Schemas für Pump Metric

Dieser Ordner enthält alle SQL-Schemas und Migrationen für das Pump Metric System.

## 📋 Dateien

### `schema.sql`
**Hauptschema** - Vereinfachte Version für schnelle Referenz. Enthält die `coin_metrics` Tabelle mit allen Spalten und Indizes.

**Verwendung**: Für schnelle Übersicht und als Basis-Schema.

### `coin_metrics_complete.sql`
**Vollständiges Schema** - Detaillierte Version mit:
- Vollständigen Kommentaren für jede Spalte
- Detaillierten Beschreibungen
- Beispiel-SQL-Abfragen
- Indizes für Performance

**Verwendung**: Für Dokumentation, Entwicklung und als Referenz für alle verfügbaren Metriken.

### `ensure_streams.sql`
**Hilfsfunktion** - Stellt sicher, dass `coin_streams` Einträge für alle aktiven Coins existieren.

**Verwendung**: Wird vom Tracker automatisch verwendet.

## 🗑️ Veraltete Dateien (können gelöscht werden)

Die folgenden Migrations-Dateien sind nicht mehr nötig, da alle Spalten jetzt im Hauptschema enthalten sind:
- ~~`add_advanced_metrics.sql`~~ - Enthalten in `schema.sql` und `coin_metrics_complete.sql`
- ~~`add_ratios.sql`~~ - Enthalten in `schema.sql` und `coin_metrics_complete.sql`

## 📊 coin_metrics Tabelle

Die `coin_metrics` Tabelle speichert alle Metriken für jeden Coin in jedem Intervall.

### Kategorien

1. **Identifikation & Zeitpunkt**: `id`, `mint`, `timestamp`, `phase_id_at_time`
2. **Preis & Bewertung**: OHLC Preise, Market Cap
3. **Pump.fun Mechanik**: Bonding Curve %, Virtual SOL, KOTH Status
4. **Volumen & Fluss**: Gesamt-, Buy-, Sell-Volumen, Netto-Volumen
5. **Order-Struktur**: Anzahl Buys/Sells, Unique Wallets, Micro Trades
6. **Whale Watching**: Whale-Volumen, Anzahl Whale-Trades, Max Trades
7. **Dev-Tracking**: Verkauftes Volumen vom Creator (Rug-Pull-Erkennung)
8. **Erweiterte Metriken**: Volatilität, Durchschnittliche Trade-Größe
9. **Ratio-Metriken**: Buy-Pressure, Unique-Signer-Ratio

### Indizes

- `idx_metrics_mint_time`: Schnelle Suche nach Coin und Zeitpunkt
- `idx_metrics_timestamp`: Zeitbereichs-Abfragen
- `idx_metrics_phase`: Phase-basierte Abfragen
- `idx_metrics_koth`: KOTH-Coins

## 🚀 Verwendung

### Neue Installation

```sql
-- Verwende das vollständige Schema
\i sql/coin_metrics_complete.sql
```

### Bestehende Installation

Das System erkennt automatisch fehlende Spalten und fügt sie hinzu (siehe `tracker/db_migration.py`).

## 📖 Weitere Informationen

- **UI Info-Seite**: Detaillierte Erklärungen aller Metriken
- **Tracker Code**: `tracker/main.py` - Berechnungslogik
- **DB Migration**: `tracker/db_migration.py` - Automatische Schema-Updates
