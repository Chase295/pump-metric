# 🔄 Buffer-System (180 Sekunden) - Detaillierte Erklärung

## 📋 Übersicht

Das Buffer-System stellt sicher, dass **keine Trades verloren gehen**, auch wenn ein Coin erst mit Verzögerung in `coin_streams` aktiviert wird. Es verwendet zwei parallele WebSocket-Streams und einen Ring-Buffer.

---

## 🏗️ Architektur

### 1. **Zwei parallele WebSocket-Streams**

#### Stream 1: NewToken-Listener (Zeile 289-357)
```python
async def run_new_token_listener(self, subscribe_queue):
    # Läuft als separater asyncio Task
    # Abonniert: {"method": "subscribeNewToken"}
    # Erkennt neue Coins SOFORT bei Erstellung (txType == "create")
```

**Funktion:**
- Hört auf `subscribeNewToken` Events
- Erkennt neue Coins **sofort** bei Erstellung
- Sendet Coin-Adresse über `subscribe_queue` an Trade-Stream
- Markiert Coin in `early_subscribed_mints`

**Zeitpunkt:** Läuft **kontinuierlich** im Hintergrund

#### Stream 2: Trade-Stream (Zeile 359-610)
```python
async def run(self):
    # Haupt-WebSocket für Trade-Events
    # Abonniert: {"method": "subscribeTokenTrade", "keys": [mint1, mint2, ...]}
    # Empfängt alle Trade-Events für abonnierte Coins
```

**Funktion:**
- Empfängt Trade-Events für alle abonnierten Coins
- **Jeder Trade** wird sofort in den Buffer gespeichert
- Wenn Coin bereits aktiv ist → Trade wird sofort verarbeitet
- Wenn Coin noch nicht aktiv ist → Trade bleibt im Buffer

**Zeitpunkt:** Läuft **kontinuierlich** parallel zum NewToken-Listener

---

## 💾 Trade-Buffer (Ring-Buffer)

### Struktur
```python
self.trade_buffer = {
    "mint_address_1": [
        (timestamp_1, trade_data_1),
        (timestamp_2, trade_data_2),
        ...
    ],
    "mint_address_2": [...],
    ...
}
```

### Speicherung (Zeile 619-631)
```python
def add_trade_to_buffer(self, data):
    mint = data["mint"]
    if mint not in self.trade_buffer:
        self.trade_buffer[mint] = []
    
    trade_entry = (time.time(), data)  # Unix-Timestamp + Trade-Daten
    self.trade_buffer[mint].append(trade_entry)
    
    # Begrenzung: Max 5000 Trades pro Coin
    if len(self.trade_buffer[mint]) > 5000:
        self.trade_buffer[mint] = self.trade_buffer[mint][-5000:]
```

**Wann wird gespeichert?**
- **JEDER** Trade, der über den Trade-Stream empfangen wird (Zeile 543-544)
- Unabhängig davon, ob der Coin bereits aktiv ist oder nicht

**Größe:**
- Max 5000 Trades pro Coin (verhindert Speicher-Überlauf)
- Bei 180 Sekunden = ~27 Trades/Sekunde möglich

---

## 🧹 Cleanup (alle 10 Sekunden)

### Funktion (Zeile 633-655)
```python
def cleanup_old_trades_from_buffer(self, now_ts):
    cutoff_time = now_ts - TRADE_BUFFER_SECONDS  # 180 Sekunden zurück
    total_removed = 0
    
    for mint in list(self.trade_buffer.keys()):
        # Entferne alle Trades älter als 180 Sekunden
        self.trade_buffer[mint] = [
            (ts, data) for ts, data in self.trade_buffer[mint]
            if ts > cutoff_time
        ]
        
        # Entferne leere Einträge
        if not self.trade_buffer[mint]:
            del self.trade_buffer[mint]
    
    return total_removed
```

**Wann läuft es?** (Zeile 581-586)
```python
# Buffer-Cleanup alle 10 Sekunden
if now_ts - self.last_buffer_cleanup > 10:
    removed = self.cleanup_old_trades_from_buffer(now_ts)
    if removed > 0:
        print(f"🧹 Buffer-Cleanup: {removed} alte Trades entfernt")
    self.last_buffer_cleanup = now_ts
```

**Zweck:**
- Verhindert unbegrenztes Wachstum des Buffers
- Entfernt Trades, die älter als 180 Sekunden sind
- Hält Speicherverbrauch niedrig

---

## 🔄 Rückwirkende Verarbeitung

### Wann wird ausgelöst? (Zeile 507-517)
```python
if is_early_subscribed or has_buffer:
    # Coin wurde bereits abonniert - verarbeite Buffer rückwirkend
    buffer_trades = self.process_trades_from_buffer(mint, created_at, started_at)
```

**Bedingungen:**
1. Coin wurde über NewToken-Listener bereits abonniert (`is_early_subscribed`)
2. ODER Coin hat Trades im Buffer (`has_buffer`)

**Zeitpunkt:** Wenn ein Coin in `coin_streams` aktiviert wird (`is_active = TRUE`)

### Verarbeitungslogik (Zeile 657-714)
```python
def process_trades_from_buffer(self, mint, created_at, started_at):
    # 1. Zeitfenster berechnen
    created_ts = created_at.timestamp()  # Wann wurde Coin erstellt?
    now_ts = time.time()                  # Jetzt
    cutoff_ts = max(created_ts, now_ts - TRADE_BUFFER_SECONDS)  # Max 180s zurück
    end_ts = now_ts                       # Bis jetzt
    
    # 2. Relevante Trades finden
    relevant_trades = []
    for trade_ts, trade_data in self.trade_buffer[mint]:
        if cutoff_ts <= trade_ts <= end_ts:
            relevant_trades.append((trade_ts, trade_data))
    
    # 3. Chronologisch sortieren (älteste zuerst)
    relevant_trades.sort(key=lambda x: x[0])
    
    # 4. Verarbeiten
    for trade_ts, trade_data in relevant_trades:
        self.process_trade(trade_data)  # Fügt Trade zu Coin-Buffer hinzu
        processed_count += 1
```

**Wichtig:**
- Trades werden **chronologisch** verarbeitet (älteste zuerst)
- Nur Trades im Zeitfenster `[created_at, jetzt]` werden verarbeitet
- Maximal 180 Sekunden zurück (wenn Coin älter ist, gehen frühe Trades verloren)

---

## 🔍 Ablauf-Diagramm

```
Zeitpunkt 0s:  Coin wird erstellt
                ↓
Zeitpunkt 0.1s: NewToken-Listener erkennt Coin
                ↓
Zeitpunkt 0.2s: Coin wird zum Trade-Stream abonniert
                ↓
Zeitpunkt 5s:   Erste Trades passieren
                → Werden in Buffer gespeichert ✅
                ↓
Zeitpunkt 10s:  Weitere Trades
                → Werden in Buffer gespeichert ✅
                ↓
Zeitpunkt 40s:  Coin wird in coin_streams aktiviert
                ↓
Zeitpunkt 40.1s: Tracker erkennt neuen Coin
                ↓
Zeitpunkt 40.2s: process_trades_from_buffer() wird aufgerufen
                ↓
Zeitpunkt 40.3s: Alle Trades von 0s-40s werden rückwirkend verarbeitet ✅
                ↓
Zeitpunkt 40.4s: Coin ist aktiv, neue Trades werden sofort verarbeitet
```

---

## ✅ Wie kann ich sicherstellen, dass es funktioniert?

### 1. **Logs prüfen**

Suche nach folgenden Log-Meldungen:

#### NewToken-Listener startet:
```
🚀 Starte NewToken-Listener (zweiter Stream für subscribeNewToken)...
✅ NewToken-Listener verbunden! Abonniere subscribeNewToken...
📡 subscribeNewToken aktiv - warte auf neue Coins...
```

#### Neuer Coin wird erkannt:
```
🆕 Neuer Coin erkannt: ABC12345... - abonniere SOFORT für 180s Buffer!
✅ ABC12345... sofort abonniert - Trades werden 180s (3 Minuten) im Buffer gespeichert
📡 ABC12345... über NewToken-Listener abonniert
```

#### Trades werden im Buffer gespeichert:
```
# Jeder Trade wird automatisch gespeichert (kein explizites Log)
# Aber: Prometheus-Metrik tracker_buffer_trades_total steigt
```

#### Buffer wird verarbeitet:
```
🔍 ABC12345...: Prüfe Buffer - created_ts=..., started_ts=..., now_ts=...
🔍 ABC12345...: Buffer hat 15 Trades
🔍 ABC12345...: 15 relevante Trades gefunden für rückwirkende Verarbeitung
🔄 Buffer: 15 rückwirkende Trades für ABC12345... verarbeitet (Zeitraum: 40s)
✅ ABC12345...: 15 Trades aus Buffer verarbeitet
```

#### Cleanup:
```
🧹 Buffer-Cleanup: 5 alte Trades entfernt
```

### 2. **Health-Check Endpoint prüfen**

```bash
curl http://localhost:8009/health | jq '.buffer_stats'
```

**Erwartete Ausgabe:**
```json
{
  "total_trades_in_buffer": 42,
  "coins_with_buffer": 3,
  "buffer_details": {
    "ABC12345...": 15,
    "DEF67890...": 20,
    "GHI11111...": 7
  }
}
```

### 3. **Prometheus-Metriken prüfen**

```bash
curl http://localhost:8009/metrics | grep buffer
```

**Wichtige Metriken:**
- `tracker_trade_buffer_size`: Anzahl Coins mit Trades im Buffer
- `tracker_buffer_trades_total`: Gesamtanzahl Trades die im Buffer gespeichert wurden
- `tracker_trades_from_buffer_total`: Anzahl Trades die aus dem Buffer verarbeitet wurden

### 4. **Manueller Test**

1. **Aktiviere einen Test-Coin manuell:**
   ```sql
   UPDATE coin_streams 
   SET is_active = TRUE, started_at = NOW() 
   WHERE token_address = 'DEINE_TEST_COIN_ADRESSE';
   ```

2. **Prüfe Logs:**
   - Suche nach `🔄 Buffer: X rückwirkende Trades`
   - Prüfe ob `tracker_trades_from_buffer_total` steigt

3. **Prüfe Datenbank:**
   ```sql
   SELECT COUNT(*) 
   FROM coin_metrics 
   WHERE mint = 'DEINE_TEST_COIN_ADRESSE' 
   AND timestamp >= (NOW() - INTERVAL '5 minutes');
   ```

---

## ⚠️ Mögliche Probleme & Lösungen

### Problem 1: NewToken-Listener läuft nicht
**Symptom:** Keine Logs von `🆕 Neuer Coin erkannt`

**Lösung:**
- Prüfe ob NewToken-Listener Task läuft
- Prüfe WebSocket-Verbindung
- Prüfe Logs auf Fehler

### Problem 2: Trades werden nicht im Buffer gespeichert
**Symptom:** `tracker_buffer_trades_total` steigt nicht

**Lösung:**
- Prüfe ob Trade-Stream läuft
- Prüfe ob Coin abonniert wurde
- Prüfe ob `add_trade_to_buffer()` aufgerufen wird

### Problem 3: Buffer wird nicht verarbeitet
**Symptom:** `tracker_trades_from_buffer_total` bleibt bei 0

**Lösung:**
- Prüfe ob Coin in `early_subscribed_mints` oder `trade_buffer` ist
- Prüfe Zeitfenster (muss zwischen `created_at` und `now` liegen)
- Prüfe ob Coin in `watchlist` ist (muss vor `process_trade()` sein)

### Problem 4: Trades gehen trotzdem verloren
**Symptom:** Metriken zeigen Lücken

**Mögliche Ursachen:**
- Coin wurde **vor** 180 Sekunden erstellt (Buffer zu klein)
- NewToken-Listener war offline
- Trade-Stream war offline
- Coin wurde nicht abonniert

**Lösung:**
- Erhöhe `TRADE_BUFFER_SECONDS` (aktuell 180s)
- Prüfe WebSocket-Verbindungen
- Prüfe Logs auf Fehler

---

## 📊 Monitoring

### Wichtige Metriken

1. **Buffer-Größe:**
   - `tracker_trade_buffer_size`: Sollte > 0 sein wenn neue Coins erkannt werden
   - `total_trades_in_buffer`: Sollte steigen wenn Trades empfangen werden

2. **Buffer-Verarbeitung:**
   - `tracker_trades_from_buffer_total`: Sollte steigen wenn Coins aktiviert werden
   - Verhältnis: `trades_from_buffer / buffer_trades_total` sollte > 0 sein

3. **WebSocket-Status:**
   - `ws_connected`: Muss `true` sein
   - `reconnect_count`: Sollte niedrig sein

### Alarme

- **Kritisch:** `ws_connected = false` für > 60 Sekunden
- **Warnung:** `tracker_trades_from_buffer_total = 0` obwohl neue Coins aktiviert werden
- **Info:** `total_trades_in_buffer > 1000` (viele Trades im Buffer)

---

## 🔧 Konfiguration

### Environment Variables

```bash
TRADE_BUFFER_SECONDS=180  # Buffer-Dauer in Sekunden (Standard: 180 = 3 Minuten)
```

**Empfehlung:**
- **Minimum:** 60 Sekunden (1 Minute)
- **Empfohlen:** 180 Sekunden (3 Minuten)
- **Maximum:** 600 Sekunden (10 Minuten) - abhängig vom verfügbaren Speicher

---

## 📝 Zusammenfassung

Das Buffer-System funktioniert in **4 Schritten**:

1. **NewToken-Listener** erkennt neue Coins sofort
2. **Trade-Stream** speichert alle Trades im 180s-Buffer
3. **Cleanup** entfernt alte Trades alle 10 Sekunden
4. **Rückwirkende Verarbeitung** wenn Coin aktiviert wird

**Garantie:**
- ✅ Alle Trades innerhalb von 180 Sekunden nach Coin-Erstellung werden erfasst
- ✅ Keine Trades gehen verloren, wenn Coin innerhalb von 180s aktiviert wird
- ⚠️ Trades die **vor** der Coin-Erstellung oder **nach** 180s passieren, können verloren gehen

