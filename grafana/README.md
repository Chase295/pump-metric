# Grafana Dashboard für Pump Metric

Professionelles Monitoring-Dashboard für das Pump Metric System.

## 📊 Dashboard-Features

Das Dashboard zeigt folgende Metriken:

### 1. System-Status (Top-Row)
- **WebSocket Status**: Verbindungsstatus (Online/Offline)
- **Datenbank Status**: DB-Verbindungsstatus (Online/Offline)
- **Uptime**: System-Uptime in Sekunden
- **Aktuell getrackte Coins**: Anzahl der aktiven Coins

### 2. Trade-Statistiken
- **Trade-Rate (pro Sekunde)**: Rate der empfangenen, verarbeiteten und aus Buffer verarbeiteten Trades
- **Trade-Statistiken (Gesamt)**: Kumulative Werte für alle Trades

### 3. Buffer-System
- **Trades im Buffer**: Aktuelle Anzahl der Trades im Buffer
- **Gesamt im Buffer gespeichert**: Gesamtanzahl der im Buffer gespeicherten Trades

### 4. Coin Lifecycle
- **Graduierte Coins**: Anzahl der zu Raydium graduierten Coins
- **Beendete Coins**: Anzahl der beendeten Coins
- **Phasen-Wechsel**: Anzahl der Phasen-Wechsel

### 5. Performance-Metriken
- **DB Query Performance**: p50, p95, p99 und Durchschnitt der DB-Query-Latenz
- **Flush Performance**: p50, p95, p99 und Durchschnitt der Flush-Latenz
- **Operationen pro Sekunde**: DB Queries und Flushes pro Sekunde

### 6. System-Health
- **WebSocket Reconnects**: Anzahl der Reconnects
- **DB Fehler**: Anzahl der DB-Fehler in der letzten Stunde
- **Verbindungsdauer**: Dauer der aktuellen Verbindung
- **Metriken gespeichert (Rate)**: Rate der gespeicherten Metriken

### 7. System-Ressourcen
- **Memory Usage**: RAM und Virtual Memory
- **CPU Usage**: CPU-Auslastung
- **File Descriptors**: Offene und maximale File Descriptors

## 🚀 Installation

### Schritt 1: Prometheus konfigurieren

Stelle sicher, dass Prometheus die Metriken vom Tracker-Service scraped:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'pump-metric'
    scrape_interval: 10s
    static_configs:
      - targets: ['DEINE_IP:8011']  # Tracker API Port
```

### Schritt 2: Grafana Dashboard importieren

1. Öffne Grafana → **Dashboards** → **Import**
2. Klicke auf **Upload JSON file**
3. Wähle die Datei: `grafana/pump-metric-dashboard.json`
4. Oder kopiere den Inhalt der JSON-Datei und füge ihn ein

### Schritt 3: Prometheus Data Source konfigurieren

1. Gehe zu **Configuration** → **Data Sources**
2. Füge **Prometheus** hinzu (falls noch nicht vorhanden)
3. URL: `http://DEINE_PROMETHEUS_IP:9090`
4. Speichere und teste die Verbindung

### Schritt 4: Dashboard anpassen

Nach dem Import:
1. Klicke auf das Zahnrad-Symbol (⚙️) oben rechts
2. Gehe zu **Variables** (falls nötig)
3. Stelle sicher, dass `${DS_PROMETHEUS}` auf deine Prometheus Data Source zeigt

## 📈 Verwendung

### Auto-Refresh
Das Dashboard aktualisiert sich automatisch alle **10 Sekunden**.

### Zeitbereich
Standard: **Letzte 6 Stunden**
- Kann oben rechts angepasst werden
- Verfügbare Optionen: 15m, 30m, 1h, 6h, 12h, 24h, 7d, 30d

### Metriken-Erklärung

#### Trade-Rate
- Zeigt die Rate der Trades pro Sekunde
- **Trades empfangen**: Alle vom WebSocket empfangenen Trades
- **Trades verarbeitet**: Erfolgreich verarbeitete Trades
- **Trades aus Buffer**: Trades die aus dem 180s-Buffer verarbeitet wurden

#### Performance-Metriken
- **p50**: 50% der Queries sind schneller als dieser Wert
- **p95**: 95% der Queries sind schneller als dieser Wert
- **p99**: 99% der Queries sind schneller als dieser Wert
- **Durchschnitt**: Durchschnittliche Latenz

#### Buffer-System
- **Trades im Buffer**: Aktuelle Anzahl (sollte < 1000 sein)
- **Gesamt gespeichert**: Gesamtanzahl seit Start

## 🔧 Anpassungen

### Metriken hinzufügen
1. Klicke auf **Edit** (Stift-Symbol)
2. Klicke auf **Add** → **Visualization**
3. Wähle **Prometheus** als Data Source
4. Füge deine Query hinzu (z.B. `tracker_coins_tracked`)

### Alerts konfigurieren
1. Klicke auf ein Panel → **Edit**
2. Gehe zu **Alert** Tab
3. Erstelle eine Alert-Regel
4. Beispiel: Alert wenn `tracker_ws_connected == 0`

## 📊 Beispiel-Alerts

### WebSocket offline
```promql
tracker_ws_connected == 0
```

### DB offline
```promql
tracker_db_connected == 0
```

### Zu viele Trades im Buffer
```promql
tracker_trade_buffer_size > 5000
```

### Hohe DB-Latenz
```promql
histogram_quantile(0.95, rate(tracker_db_query_duration_seconds_bucket[5m])) > 0.1
```

## 🎨 Dashboard-Layout

Das Dashboard ist in folgende Bereiche unterteilt:

1. **Zeile 1**: System-Status (4 Panels)
2. **Zeile 2-3**: Trade-Statistiken (2 große Panels)
3. **Zeile 4-5**: Buffer & Lifecycle (2 große Panels)
4. **Zeile 6-7**: Performance (2 große Panels)
5. **Zeile 8**: Health-Indikatoren (4 kleine Panels)
6. **Zeile 9-10**: System-Ressourcen (2 große Panels)

## 📝 Verfügbare Metriken

Alle Metriken beginnen mit `tracker_`:

- `tracker_trades_received_total` - Empfangene Trades (Counter)
- `tracker_trades_processed_total` - Verarbeitete Trades (Counter)
- `tracker_trades_from_buffer_total` - Aus Buffer verarbeitet (Counter)
- `tracker_metrics_saved_total` - Gespeicherte Metriken (Counter)
- `tracker_coins_tracked` - Aktuell getrackte Coins (Gauge)
- `tracker_coins_graduated_total` - Graduierte Coins (Counter)
- `tracker_coins_finished_total` - Beendete Coins (Counter)
- `tracker_phase_switches_total` - Phasen-Wechsel (Counter)
- `tracker_ws_connected` - WebSocket Status (Gauge: 0/1)
- `tracker_db_connected` - DB Status (Gauge: 0/1)
- `tracker_uptime_seconds` - Uptime (Gauge)
- `tracker_ws_reconnects_total` - Reconnects (Counter)
- `tracker_db_errors_total` - DB Fehler (Counter)
- `tracker_trade_buffer_size` - Buffer-Größe (Gauge)
- `tracker_buffer_trades_total` - Buffer Trades gesamt (Counter)
- `tracker_db_query_duration_seconds` - DB Query Latenz (Histogram)
- `tracker_flush_duration_seconds` - Flush Latenz (Histogram)

## 🔗 Weitere Ressourcen

- **Prometheus Metrics Endpoint**: `http://DEINE_IP:8011/metrics`
- **Health Check Endpoint**: `http://DEINE_IP:8011/health`
- **UI Dashboard**: `http://DEINE_IP:8501`

## 💡 Tipps

1. **Export als PDF**: Klicke auf das Share-Symbol → **Export PDF**
2. **Snapshot erstellen**: Für schnelle Momentaufnahmen
3. **Playlist**: Erstelle eine Playlist für mehrere Dashboards
4. **Annotations**: Füge Annotations hinzu für wichtige Events

---

**Erstellt**: 2025-01-26  
**Version**: 1.0  
**Grafana Version**: 10.0.0+

