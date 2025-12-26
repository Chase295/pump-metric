# http://100.76.209.59:4002/metrics
FROM python:3.11-slim

WORKDIR /app

# Installation der benötigten Pakete inkl. Prometheus Client
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir asyncpg websockets python-dateutil aiohttp prometheus-client

# Erstelle main.py mit Prometheus Metrics
# FIX: metrics_handler angepasst für aiohttp charset Trennung
RUN printf '%s\n' \
'import asyncio' \
'import websockets' \
'import json' \
'import time' \
'import asyncpg' \
'import os' \
'from datetime import datetime, timezone' \
'from dateutil import parser' \
'from zoneinfo import ZoneInfo' \
'from collections import Counter' \
'from aiohttp import web' \
'from prometheus_client import Counter as PromCounter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST' \
'' \
'# --- KONFIGURATION ---' \
'DB_DSN = os.getenv("DB_DSN", "postgresql://postgres:9HVxi6hN6j7xpmqUx84o@100.118.155.75:5432/crypto")' \
'WS_URI = os.getenv("WS_URI", "wss://pumpportal.fun/api/data")' \
'DB_REFRESH_INTERVAL = int(os.getenv("DB_REFRESH_INTERVAL", "10"))' \
'SOL_RESERVES_FULL = float(os.getenv("SOL_RESERVES_FULL", "85.0"))' \
'AGE_CALCULATION_OFFSET_MIN = int(os.getenv("AGE_CALCULATION_OFFSET_MIN", "60"))' \
'DB_RETRY_DELAY = int(os.getenv("DB_RETRY_DELAY", "5"))' \
'WS_RETRY_DELAY = int(os.getenv("WS_RETRY_DELAY", "3"))' \
'WS_MAX_RETRY_DELAY = int(os.getenv("WS_MAX_RETRY_DELAY", "60"))' \
'WS_PING_INTERVAL = int(os.getenv("WS_PING_INTERVAL", "20"))' \
'WS_PING_TIMEOUT = int(os.getenv("WS_PING_TIMEOUT", "10"))' \
'WS_CONNECTION_TIMEOUT = int(os.getenv("WS_CONNECTION_TIMEOUT", "30"))' \
'HEALTH_PORT = 8000' \
'' \
'# ZEITZONEN' \
'GERMAN_TZ = ZoneInfo("Europe/Berlin")' \
'' \
'# --- PROMETHEUS METRICS ---' \
'trades_received = PromCounter("tracker_trades_received_total", "Anzahl empfangener Trades")' \
'trades_processed = PromCounter("tracker_trades_processed_total", "Anzahl verarbeiteter Trades")' \
'metrics_saved = PromCounter("tracker_metrics_saved_total", "Anzahl gespeicherter Metriken")' \
'coins_tracked = Gauge("tracker_coins_tracked", "Anzahl aktuell getrackter Coins")' \
'coins_graduated = PromCounter("tracker_coins_graduated_total", "Anzahl graduierter Coins")' \
'coins_finished = PromCounter("tracker_coins_finished_total", "Anzahl beendeter Coins")' \
'phase_switches = PromCounter("tracker_phase_switches_total", "Anzahl Phasen-Wechsel")' \
'db_errors = PromCounter("tracker_db_errors_total", "DB Fehler", ["type"])' \
'ws_reconnects = PromCounter("tracker_ws_reconnects_total", "WebSocket Reconnects")' \
'ws_connected = Gauge("tracker_ws_connected", "WebSocket Status (1=connected)")' \
'db_connected = Gauge("tracker_db_connected", "DB Status (1=connected)")' \
'uptime_seconds = Gauge("tracker_uptime_seconds", "Uptime in Sekunden")' \
'last_trade_timestamp = Gauge("tracker_last_trade_timestamp", "Timestamp des letzten Trades")' \
'connection_duration = Gauge("tracker_connection_duration_seconds", "Dauer der aktuellen Verbindung")' \
'db_query_duration = Histogram("tracker_db_query_duration_seconds", "Dauer von DB-Queries")' \
'flush_duration = Histogram("tracker_flush_duration_seconds", "Dauer von Metric-Flushes")' \
'' \
'# --- STATUS TRACKING ---' \
'tracker_status = {' \
'    "db_connected": False,' \
'    "ws_connected": False,' \
'    "last_error": None,' \
'    "start_time": time.time(),' \
'    "connection_start": None,' \
'    "last_message_time": None,' \
'    "reconnect_count": 0,' \
'    "total_trades": 0,' \
'    "total_metrics_saved": 0' \
'}' \
'' \
'async def metrics_handler(request):' \
'    """Prometheus Metrics Endpoint"""' \
'    uptime_seconds.set(time.time() - tracker_status["start_time"])' \
'    if tracker_status["connection_start"]:' \
'        connection_duration.set(time.time() - tracker_status["connection_start"])' \
'    return web.Response(body=generate_latest(), content_type="text/plain; version=0.0.4", charset="utf-8")' \
'' \
'async def health_check(request):' \
'    db_status = tracker_status.get("db_connected", False)' \
'    ws_status = tracker_status.get("ws_connected", False)' \
'    uptime = time.time() - tracker_status["start_time"]' \
'    last_msg = tracker_status.get("last_message_time")' \
'    ' \
'    health_data = {' \
'        "status": "healthy" if (db_status and ws_status) else "degraded",' \
'        "db_connected": db_status,' \
'        "ws_connected": ws_status,' \
'        "uptime_seconds": int(uptime),' \
'        "total_trades": tracker_status["total_trades"],' \
'        "total_metrics_saved": tracker_status["total_metrics_saved"],' \
'        "last_message_ago": int(time.time() - last_msg) if last_msg else None,' \
'        "reconnect_count": tracker_status["reconnect_count"],' \
'        "last_error": tracker_status.get("last_error")' \
'    }' \
'    ' \
'    status_code = 200 if (db_status and ws_status) else 503' \
'    return web.json_response(health_data, status=status_code)' \
'' \
'async def start_health_server():' \
'    app = web.Application()' \
'    app.add_routes([' \
'        web.get("/health", health_check),' \
'        web.get("/metrics", metrics_handler)' \
'    ])' \
'    runner = web.AppRunner(app)' \
'    await runner.setup()' \
'    site = web.TCPSite(runner, "0.0.0.0", HEALTH_PORT)' \
'    print(f"🏥 Health-Check Server läuft auf Port {HEALTH_PORT}", flush=True)' \
'    print(f"📊 Prometheus Metrics auf http://localhost:{HEALTH_PORT}/metrics", flush=True)' \
'    await site.start()' \
'' \
'class Tracker:' \
'    def __init__(self):' \
'        self.pool = None' \
'        self.phases_config = {}' \
'        self.watchlist = {}' \
'        self.subscribed_mints = set()' \
'        self.sorted_phase_ids = []' \
'' \
'    async def init_db_connection(self):' \
'        while True:' \
'            try:' \
'                if self.pool:' \
'                    await self.pool.close()' \
'                self.pool = await asyncpg.create_pool(DB_DSN, min_size=1, max_size=10)' \
'                rows = await self.pool.fetch("SELECT * FROM ref_coin_phases ORDER BY id ASC")' \
'                self.phases_config = {}' \
'                for row in rows:' \
'                    self.phases_config[row["id"]] = {' \
'                        "interval": row["interval_seconds"],' \
'                        "max_age": row["max_age_minutes"],' \
'                        "name": row["name"]' \
'                    }' \
'                self.sorted_phase_ids = sorted(self.phases_config.keys())' \
'                print(f"✅ DB verbunden. Geladene Phasen: {self.sorted_phase_ids}", flush=True)' \
'                tracker_status["db_connected"] = True' \
'                tracker_status["last_error"] = None' \
'                db_connected.set(1)' \
'                return' \
'            except Exception as e:' \
'                tracker_status["db_connected"] = False' \
'                tracker_status["last_error"] = f"db_error: {str(e)[:100]}"' \
'                db_connected.set(0)' \
'                db_errors.labels(type="connection").inc()' \
'                print(f"❌ DB Verbindungsfehler: {e}", flush=True)' \
'                print(f"⏳ Retry in {DB_RETRY_DELAY}s...", flush=True)' \
'                await asyncio.sleep(DB_RETRY_DELAY)' \
'' \
'    async def get_active_streams(self):' \
'        try:' \
'            with db_query_duration.time():' \
'                sql = """' \
'                    SELECT cs.token_address, cs.current_phase_id, dc.token_created_at' \
'                    FROM coin_streams cs' \
'                    JOIN discovered_coins dc ON cs.token_address = dc.token_address' \
'                    WHERE cs.is_active = TRUE' \
'                """' \
'                rows = await self.pool.fetch(sql)' \
'                results = {}' \
'                for row in rows:' \
'                    mint = row["token_address"]' \
'                    created_at = row["token_created_at"]' \
'                    if not created_at: created_at = datetime.now(timezone.utc)' \
'                    if created_at.tzinfo is None: created_at = created_at.replace(tzinfo=timezone.utc)' \
'                    results[mint] = {"phase_id": row["current_phase_id"], "created_at": created_at}' \
'                return results' \
'        except Exception as e:' \
'            print(f"⚠️ DB Query Error: {e}", flush=True)' \
'            tracker_status["db_connected"] = False' \
'            db_connected.set(0)' \
'            db_errors.labels(type="query").inc()' \
'            raise' \
'' \
'    async def switch_phase(self, mint, old_phase, new_phase):' \
'        try:' \
'            print(f"🆙 UPGRADE: {mint} Phase {old_phase} -> {new_phase}", flush=True)' \
'            async with self.pool.acquire() as conn:' \
'                await conn.execute("UPDATE coin_streams SET current_phase_id = $1 WHERE token_address = $2", new_phase, mint)' \
'            phase_switches.inc()' \
'        except Exception as e:' \
'            print(f"⚠️ Phase Switch Error: {e}", flush=True)' \
'            tracker_status["db_connected"] = False' \
'            db_connected.set(0)' \
'            db_errors.labels(type="update").inc()' \
'' \
'    async def stop_tracking(self, mint, is_graduation=False):' \
'        try:' \
'            if is_graduation:' \
'                print(f"🎉 GRADUATION: {mint} geht zu Raydium! Tracking beendet.", flush=True)' \
'                final_phase = 100' \
'                graduated_flag = True' \
'                coins_graduated.inc()' \
'            else:' \
'                print(f"🏁 FINISHED: {mint} Lifecycle beendet.", flush=True)' \
'                final_phase = 99' \
'                graduated_flag = False' \
'                coins_finished.inc()' \
'            async with self.pool.acquire() as conn:' \
'                await conn.execute("""' \
'                    UPDATE coin_streams' \
'                    SET is_active = FALSE,' \
'                        current_phase_id = $2,' \
'                        is_graduated = $3' \
'                    WHERE token_address = $1' \
'                """, mint, final_phase, graduated_flag)' \
'        except Exception as e:' \
'            print(f"⚠️ Stop Tracking Error: {e}", flush=True)' \
'            tracker_status["db_connected"] = False' \
'            db_connected.set(0)' \
'            db_errors.labels(type="update").inc()' \
'        finally:' \
'            if mint in self.watchlist: del self.watchlist[mint]' \
'            if mint in self.subscribed_mints: self.subscribed_mints.remove(mint)' \
'            coins_tracked.set(len(self.watchlist))' \
'' \
'    def get_empty_buffer(self):' \
'        return {' \
'            "open": None, "high": -1, "low": float("inf"), "close": 0,' \
'            "vol": 0, "vol_buy": 0, "vol_sell": 0, "buys": 0, "sells": 0,' \
'            "micro_trades": 0, "max_buy": 0, "max_sell": 0,' \
'            "wallets": set(), "v_sol": 0, "mcap": 0' \
'        }' \
'' \
'    async def run(self):' \
'        await self.init_db_connection()' \
'        reconnect_count = 0' \
'        ' \
'        while True:' \
'            try:' \
'                print(f"🔌 Verbinde zu WebSocket... (Versuch #{reconnect_count + 1})", flush=True)' \
'                ' \
'                async with websockets.connect(' \
'                    WS_URI,' \
'                    ping_interval=WS_PING_INTERVAL,' \
'                    ping_timeout=WS_PING_TIMEOUT,' \
'                    close_timeout=10,' \
'                    max_size=2**23,' \
'                    compression=None' \
'                ) as ws:' \
'                    tracker_status["ws_connected"] = True' \
'                    tracker_status["connection_start"] = time.time()' \
'                    tracker_status["last_error"] = None' \
'                    ws_connected.set(1)' \
'                    reconnect_count = 0' \
'                    tracker_status["reconnect_count"] = 0' \
'                    ' \
'                    print("✅ WebSocket verbunden! Tracker läuft...", flush=True)' \
'                    ' \
'                    last_refresh = 0' \
'                    last_message_time = time.time()' \
'                    ' \
'                    while True:' \
'                        now_ts = time.time()' \
'                        ' \
'                        if now_ts - last_refresh > DB_REFRESH_INTERVAL:' \
'                            try:' \
'                                db_streams = await self.get_active_streams()' \
'                                current_set = set(db_streams.keys())' \
'                                to_remove = self.subscribed_mints - current_set' \
'                                ' \
'                                if to_remove:' \
'                                    for mint in to_remove:' \
'                                        if mint in self.watchlist: del self.watchlist[mint]' \
'                                        self.subscribed_mints.remove(mint)' \
'                                ' \
'                                to_add = current_set - self.subscribed_mints' \
'                                if to_add:' \
'                                    await ws.send(json.dumps({"method": "subscribeTokenTrade", "keys": list(to_add)}))' \
'                                    for mint in to_add:' \
'                                        p_id = db_streams[mint]["phase_id"]' \
'                                        if p_id not in self.phases_config:' \
'                                            p_id = self.sorted_phase_ids[0] if self.sorted_phase_ids else 1' \
'                                        interval = self.phases_config[p_id]["interval"]' \
'                                        self.watchlist[mint] = {' \
'                                            "meta": db_streams[mint],' \
'                                            "buffer": self.get_empty_buffer(),' \
'                                            "next_flush": now_ts + interval,' \
'                                            "interval": interval' \
'                                        }' \
'                                        self.subscribed_mints.add(mint)' \
'                                ' \
'                                tracker_status["db_connected"] = True' \
'                                db_connected.set(1)' \
'                                coins_tracked.set(len(self.watchlist))' \
'                                last_refresh = now_ts' \
'                            except Exception as e:' \
'                                print(f"⚠️ DB Sync Error: {e}. Weiter ohne DB-Update...", flush=True)' \
'                                tracker_status["db_connected"] = False' \
'                                db_connected.set(0)' \
'                                last_refresh = now_ts' \
'                        ' \
'                        try:' \
'                            msg = await asyncio.wait_for(ws.recv(), timeout=1.0)' \
'                            last_message_time = time.time()' \
'                            tracker_status["last_message_time"] = last_message_time' \
'                            ' \
'                            data = json.loads(msg)' \
'                            trades_received.inc()' \
'                            ' \
'                            if "txType" in data and data["mint"] in self.watchlist:' \
'                                self.process_trade(data)' \
'                                trades_processed.inc()' \
'                                tracker_status["total_trades"] += 1' \
'                                last_trade_timestamp.set(time.time())' \
'                        ' \
'                        except asyncio.TimeoutError:' \
'                            if time.time() - last_message_time > WS_CONNECTION_TIMEOUT:' \
'                                print(f"⚠️ Keine Nachrichten seit {WS_CONNECTION_TIMEOUT}s - Reconnect", flush=True)' \
'                                raise websockets.exceptions.ConnectionClosed(1006, "Timeout")' \
'                        ' \
'                        except websockets.exceptions.ConnectionClosed as e:' \
'                            print(f"🔌 WebSocket Verbindung geschlossen: {e}", flush=True)' \
'                            tracker_status["ws_connected"] = False' \
'                            tracker_status["last_error"] = f"ws_closed: {str(e)[:100]}"' \
'                            ws_connected.set(0)' \
'                            break' \
'                        ' \
'                        except json.JSONDecodeError as e:' \
'                            print(f"⚠️ JSON Fehler: {e}", flush=True)' \
'                            continue' \
'                        ' \
'                        except Exception as e:' \
'                            print(f"⚠️ WS Receive Error: {e}", flush=True)' \
'                            tracker_status["last_error"] = f"ws_error: {str(e)[:100]}"' \
'                            break' \
'                        ' \
'                        await self.check_lifecycle_and_flush(now_ts)' \
'            ' \
'            except websockets.exceptions.WebSocketException as e:' \
'                tracker_status["ws_connected"] = False' \
'                tracker_status["last_error"] = f"ws_exception: {str(e)[:100]}"' \
'                ws_connected.set(0)' \
'                ws_reconnects.inc()' \
'                print(f"❌ WebSocket Exception: {e}", flush=True)' \
'                reconnect_count += 1' \
'                tracker_status["reconnect_count"] = reconnect_count' \
'            ' \
'            except Exception as e:' \
'                tracker_status["ws_connected"] = False' \
'                tracker_status["last_error"] = f"unexpected: {str(e)[:100]}"' \
'                ws_connected.set(0)' \
'                ws_reconnects.inc()' \
'                print(f"❌ Unerwarteter Fehler: {e}", flush=True)' \
'                reconnect_count += 1' \
'                tracker_status["reconnect_count"] = reconnect_count' \
'            ' \
'            delay = min(WS_RETRY_DELAY * (1 + reconnect_count * 0.5), WS_MAX_RETRY_DELAY)' \
'            print(f"⏳ Reconnect in {delay:.1f}s...", flush=True)' \
'            await asyncio.sleep(delay)' \
'            ' \
'            if not tracker_status["db_connected"]:' \
'                print("🔄 DB auch getrennt, versuche Reconnect...", flush=True)' \
'                await self.init_db_connection()' \
'' \
'    def process_trade(self, data):' \
'        mint = data["mint"]' \
'        if mint not in self.watchlist: return' \
'        entry = self.watchlist[mint]' \
'        buf = entry["buffer"]' \
'        try:' \
'            sol = float(data["solAmount"])' \
'            price = float(data["vSolInBondingCurve"]) / float(data["vTokensInBondingCurve"])' \
'            is_buy = data["txType"] == "buy"' \
'        except: return' \
'        if buf["open"] is None: buf["open"] = price' \
'        buf["close"] = price' \
'        buf["high"] = max(buf["high"], price)' \
'        buf["low"] = min(buf["low"], price)' \
'        buf["vol"] += sol' \
'        if is_buy:' \
'            buf["buys"] += 1' \
'            buf["vol_buy"] += sol' \
'            buf["max_buy"] = max(buf["max_buy"], sol)' \
'        else:' \
'            buf["sells"] += 1' \
'            buf["vol_sell"] += sol' \
'            buf["max_sell"] = max(buf["max_sell"], sol)' \
'        if sol < 0.01: buf["micro_trades"] += 1' \
'        buf["wallets"].add(data["traderPublicKey"])' \
'        buf["v_sol"] = float(data["vSolInBondingCurve"])' \
'        buf["mcap"] = price * 1_000_000_000' \
'' \
'    async def check_lifecycle_and_flush(self, now_ts):' \
'        batch_data = []' \
'        phases_in_batch = []' \
'        now_utc = datetime.now(timezone.utc)' \
'        now_berlin = datetime.now(GERMAN_TZ)' \
'        ' \
'        for mint, entry in list(self.watchlist.items()):' \
'            buf = entry["buffer"]' \
'            current_bonding_pct = (buf["v_sol"] / SOL_RESERVES_FULL) * 100' \
'            if current_bonding_pct >= 99.5:' \
'                await self.stop_tracking(mint, is_graduation=True)' \
'                continue' \
'            created_at = entry["meta"]["created_at"]' \
'            current_pid = entry["meta"]["phase_id"]' \
'            diff = now_utc - created_at' \
'            age_minutes = (diff.total_seconds() / 60) - AGE_CALCULATION_OFFSET_MIN' \
'            if age_minutes < 0: age_minutes = 0' \
'            phase_cfg = self.phases_config.get(current_pid)' \
'            if phase_cfg and age_minutes > phase_cfg["max_age"]:' \
'                next_pid = None' \
'                for pid in self.sorted_phase_ids:' \
'                    if pid > current_pid:' \
'                        next_pid = pid' \
'                        break' \
'                if next_pid is None or next_pid >= 99:' \
'                    await self.stop_tracking(mint, is_graduation=False)' \
'                    continue' \
'                else:' \
'                    await self.switch_phase(mint, current_pid, next_pid)' \
'                    entry["meta"]["phase_id"] = next_pid' \
'                    new_interval = self.phases_config[next_pid]["interval"]' \
'                    entry["interval"] = new_interval' \
'                    entry["next_flush"] = now_ts + new_interval' \
'            if now_ts >= entry["next_flush"]:' \
'                if buf["vol"] > 0:' \
'                    is_koth = buf["mcap"] > 30000' \
'                    batch_data.append((' \
'                        mint, now_berlin, entry["meta"]["phase_id"],' \
'                        buf["open"], buf["high"], buf["low"], buf["close"], buf["mcap"],' \
'                        current_bonding_pct, buf["v_sol"], is_koth,' \
'                        buf["vol"], buf["vol_buy"], buf["vol_sell"],' \
'                        buf["buys"], buf["sells"], len(buf["wallets"]), buf["micro_trades"],' \
'                        0, buf["max_buy"], buf["max_sell"]' \
'                    ))' \
'                    phases_in_batch.append(entry["meta"]["phase_id"])' \
'                entry["buffer"] = self.get_empty_buffer()' \
'                entry["next_flush"] = now_ts + entry["interval"]' \
'        ' \
'        if batch_data and tracker_status["db_connected"]:' \
'            sql = """' \
'                INSERT INTO coin_metrics (' \
'                    mint, timestamp, phase_id_at_time,' \
'                    price_open, price_high, price_low, price_close, market_cap_close,' \
'                    bonding_curve_pct, virtual_sol_reserves, is_koth,' \
'                    volume_sol, buy_volume_sol, sell_volume_sol,' \
'                    num_buys, num_sells, unique_wallets, num_micro_trades,' \
'                    dev_sold_amount, max_single_buy_sol, max_single_sell_sol' \
'                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21)' \
'            """' \
'            try:' \
'                with flush_duration.time():' \
'                    async with self.pool.acquire() as conn:' \
'                        await conn.executemany(sql, batch_data)' \
'                counts = Counter(phases_in_batch)' \
'                details = ", ".join([f"Phase {k}: {v}" for k,v in sorted(counts.items())])' \
'                print(f"💾 Saved metrics for {len(batch_data)} coins ({details})", flush=True)' \
'                metrics_saved.inc(len(batch_data))' \
'                tracker_status["total_metrics_saved"] += len(batch_data)' \
'            except Exception as e:' \
'                print(f"⚠️ SQL Error: {e}. Daten gehen verloren!", flush=True)' \
'                tracker_status["db_connected"] = False' \
'                db_connected.set(0)' \
'                db_errors.labels(type="insert").inc()' \
'        elif batch_data and not tracker_status["db_connected"]:' \
'            print(f"⚠️ {len(batch_data)} Datenpunkte verloren (DB nicht verbunden)", flush=True)' \
'' \
'async def start_tracker():' \
'    tracker = Tracker()' \
'    await tracker.run()' \
'' \
'async def main():' \
'    print(f"🔧 Konfiguration:", flush=True)' \
'    print(f"  - DB_REFRESH_INTERVAL: {DB_REFRESH_INTERVAL}s", flush=True)' \
'    print(f"  - WS_PING_INTERVAL: {WS_PING_INTERVAL}s", flush=True)' \
'    print(f"  - WS_CONNECTION_TIMEOUT: {WS_CONNECTION_TIMEOUT}s", flush=True)' \
'    print(f"  - WS_URI: {WS_URI}", flush=True)' \
'    await asyncio.gather(start_tracker(), start_health_server())' \
'' \
'if __name__ == "__main__":' \
'    try:' \
'        asyncio.run(main())' \
'    except KeyboardInterrupt:' \
'        print("\\n👋 Shutdown...", flush=True)' \
> main.py

# Port 8000 für Coolify freigeben
EXPOSE 8000

# Optimierter Healthcheck mit längeren Intervallen
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

# Graceful Shutdown
STOPSIGNAL SIGTERM

# Starten
CMD ["python", "-u", "main.py"]