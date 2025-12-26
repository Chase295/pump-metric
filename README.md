# Pump Metric

Automatisches Tracking-System für Pump.fun Coins mit detaillierten Metriken und Echtzeit-WebSocket-Verbindung.

## 🚀 Features

- **Automatisches Coin-Tracking**: Trackt alle aktiven Coins aus `coin_streams`
- **Echtzeit-Trade-Verarbeitung**: WebSocket-Verbindung zu Pump.fun für Live-Trades
- **60-Sekunden-Buffer**: Verpasste Trades werden rückwirkend verarbeitet
- **Automatische Schema-Migration**: Datenbank-Schema wird automatisch erstellt/aktualisiert
- **Prometheus-Metriken**: Detaillierte Metriken über `/metrics` Endpoint
- **Streamlit UI**: Web-Interface für Monitoring und Konfiguration
- **Coolify-ready**: Vollständig für Coolify-Deployment vorbereitet

## 📋 Voraussetzungen

- PostgreSQL Datenbank (mit `coin_streams`, `discovered_coins`, `ref_coin_phases` Tabellen)
- Docker & Docker Compose (für lokale Entwicklung)
- Coolify (für Production-Deployment)

## 🛠️ Installation

### Option 1: Coolify Deployment (Empfohlen)

1. **Repository in Coolify verbinden**:
   - Repository: `https://github.com/Chase295/pump-metric`
   - Build Pack: Docker Compose

2. **Environment Variables setzen**:
   ```
   DB_DSN=postgresql://user:password@host:5432/database
   WS_URI=wss://pumpportal.fun/api/data
   TRADE_BUFFER_SECONDS=180
   ```

3. **Deploy**: Coolify erstellt automatisch beide Services (tracker + ui)

4. **Zugriff**:
   - Tracker API: `http://your-domain:8000/health`
   - UI: `http://your-domain:8501`

### Option 2: Lokale Installation mit Docker Compose

```bash
# 1. Repository klonen
git clone https://github.com/Chase295/pump-metric.git
cd pump-metric

# 2. Environment Variables setzen
export DB_DSN="postgresql://user:password@host:5432/database"
export WS_URI="wss://pumpportal.fun/api/data"

# 3. Services starten
docker compose up -d

# 4. Logs prüfen
docker compose logs -f tracker
```

## 🔧 Konfiguration

### Environment Variables

| Variable | Default | Beschreibung |
|----------|---------|--------------|
| `DB_DSN` | - | PostgreSQL Connection String (erforderlich) |
| `WS_URI` | `wss://pumpportal.fun/api/data` | WebSocket URI für Trades |
| `DB_REFRESH_INTERVAL` | `10` | Sekunden zwischen DB-Aktualisierungen |
| `TRADE_BUFFER_SECONDS` | `180` | Buffer-Dauer in Sekunden (3 Minuten) |
| `SOL_RESERVES_FULL` | `85.0` | SOL-Betrag für vollständige Bonding Curve |
| `AGE_CALCULATION_OFFSET_MIN` | `60` | Offset für Altersberechnung in Minuten |
| `HEALTH_PORT` | `8000` | Port für Health-Check und Metriken |

### Automatische Schema-Migration

Das System erkennt automatisch fehlende Tabellen/Spalten und erstellt sie beim Start:
- `coin_metrics` Tabelle wird automatisch erstellt
- Fehlende Spalten werden automatisch hinzugefügt
- Indizes werden automatisch erstellt

**Wichtig**: Bei DB-Änderungen wird das Schema automatisch aktualisiert - kein manueller Neustart nötig!

## 📊 Datenbank-Schema

### coin_metrics

Speichert detaillierte Metriken für jeden Coin:

```sql
CREATE TABLE coin_metrics (
    id BIGINT PRIMARY KEY,
    mint VARCHAR(64) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE,
    phase_id_at_time INT,
    price_open NUMERIC,
    price_high NUMERIC,
    price_low NUMERIC,
    price_close NUMERIC,
    market_cap_close NUMERIC,
    bonding_curve_pct NUMERIC,
    virtual_sol_reserves NUMERIC,
    is_koth BOOLEAN DEFAULT FALSE,
    volume_sol NUMERIC,
    buy_volume_sol NUMERIC,
    sell_volume_sol NUMERIC,
    num_buys INT,
    num_sells INT,
    unique_wallets INT,
    num_micro_trades INT,
    dev_sold_amount NUMERIC DEFAULT 0,
    max_single_buy_sol NUMERIC DEFAULT 0,
    max_single_sell_sol NUMERIC DEFAULT 0
);
```

## 🔌 API Endpoints

### Tracker Service (Port 8000)

- `GET /health` - Health-Check mit detaillierten Status-Informationen
- `GET /metrics` - Prometheus-Metriken

### UI Service (Port 8501)

- Streamlit Web-Interface mit:
  - Dashboard mit Live-Metriken
  - Konfiguration
  - Logs (neueste zuerst)
  - Detaillierte Metriken
  - Info-Seite mit Funktionsweise

## 🔄 Funktionsweise

1. **Coin-Discovery**: Coins werden von `pump-discover` in `coin_streams` eingetragen
2. **Automatisches Tracking**: Tracker liest alle aktiven Coins aus `coin_streams`
3. **WebSocket-Subscription**: 
   - NewToken-Listener erkennt neue Coins sofort
   - Trade-Stream abonniert alle aktiven Coins
4. **Trade-Buffer**: Alle Trades werden 3 Minuten im Buffer gespeichert
5. **Rückwirkende Verarbeitung**: Bei Stream-Aktivierung werden verpasste Trades verarbeitet
6. **Metrik-Speicherung**: Metriken werden periodisch in `coin_metrics` gespeichert

## 📈 Metriken

Das System sammelt folgende Prometheus-Metriken:

- `tracker_trades_received_total` - Empfangene Trades
- `tracker_trades_processed_total` - Verarbeitete Trades
- `tracker_metrics_saved_total` - Gespeicherte Metriken
- `tracker_trades_from_buffer_total` - Aus Buffer verarbeitete Trades
- `tracker_trade_buffer_size` - Aktuelle Buffer-Größe
- `tracker_buffer_trades_total` - Gesamt Trades im Buffer
- `tracker_db_connected` - DB-Verbindungsstatus
- `tracker_ws_connected` - WebSocket-Verbindungsstatus

## 🐛 Troubleshooting

### Tracker startet nicht

1. Prüfe DB-Verbindung: `DB_DSN` korrekt gesetzt?
2. Prüfe Logs: `docker compose logs tracker`
3. Prüfe Health: `curl http://localhost:8000/health`

### Keine Metriken werden gespeichert

1. Prüfe ob Coins in `coin_streams` aktiv sind
2. Prüfe WebSocket-Verbindung in Logs
3. Prüfe Buffer-Status: `curl http://localhost:8000/health | jq .buffer_stats`

### Schema-Fehler

Das System erstellt fehlende Tabellen/Spalten automatisch. Falls Probleme auftreten:
1. Prüfe Logs auf Schema-Fehler
2. Prüfe DB-Berechtigungen
3. Manuelle Migration: `python tracker/db_migration.py`

## 📝 Entwicklung

### Lokale Entwicklung

```bash
# Services starten
docker compose up -d

# Logs verfolgen
docker compose logs -f tracker ui

# Services neu bauen
docker compose build tracker ui
docker compose up -d
```

### Code-Struktur

```
pump-metric/
├── tracker/           # Tracker Service
│   ├── main.py       # Hauptlogik
│   ├── db_migration.py  # Automatische Schema-Migration
│   └── Dockerfile
├── ui/               # Streamlit UI
│   ├── app.py
│   └── Dockerfile
├── sql/              # SQL-Schemas
│   └── schema.sql
├── docker-compose.yml
└── README.md
```

## 📄 Lizenz

MIT License

## 🤝 Beitragen

Pull Requests sind willkommen! Bitte erstelle ein Issue für größere Änderungen.

## 📧 Support

Bei Fragen oder Problemen erstelle bitte ein GitHub Issue.
