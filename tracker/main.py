import asyncio
import websockets
import json
import time
import asyncpg
import os
from datetime import datetime, timezone
from dateutil import parser
from zoneinfo import ZoneInfo
from collections import Counter
from aiohttp import web
from prometheus_client import Counter as PromCounter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from db_migration import check_and_create_schema

# --- KONFIGURATION ---
# Werte werden zuerst aus Environment Variables geladen, dann aus .env Datei überschrieben
DB_DSN = os.getenv("DB_DSN", "postgresql://postgres:9HVxi6hN6j7xpmqUx84o@100.118.155.75:5432/crypto")
WS_URI = os.getenv("WS_URI", "wss://pumpportal.fun/api/data")
DB_REFRESH_INTERVAL = int(os.getenv("DB_REFRESH_INTERVAL", "10"))
SOL_RESERVES_FULL = float(os.getenv("SOL_RESERVES_FULL", "85.0"))
AGE_CALCULATION_OFFSET_MIN = int(os.getenv("AGE_CALCULATION_OFFSET_MIN", "60"))
DB_RETRY_DELAY = int(os.getenv("DB_RETRY_DELAY", "5"))
WS_RETRY_DELAY = int(os.getenv("WS_RETRY_DELAY", "3"))
WS_MAX_RETRY_DELAY = int(os.getenv("WS_MAX_RETRY_DELAY", "60"))
WS_PING_INTERVAL = int(os.getenv("WS_PING_INTERVAL", "20"))
WS_PING_TIMEOUT = int(os.getenv("WS_PING_TIMEOUT", "10"))
WS_CONNECTION_TIMEOUT = int(os.getenv("WS_CONNECTION_TIMEOUT", "30"))
HEALTH_PORT = int(os.getenv("HEALTH_PORT", "8000"))
TRADE_BUFFER_SECONDS = int(os.getenv("TRADE_BUFFER_SECONDS", "180"))  # 180 Sekunden (3 Minuten) Buffer für verpasste Trades
WHALE_THRESHOLD_SOL = float(os.getenv("WHALE_THRESHOLD_SOL", "1.0"))  # Schwellenwert für Whale-Trades (Standard: 1.0 SOL)

def load_config_from_file():
    """Lädt Konfiguration aus .env Datei (im geteilten Volume) - überschreibt Environment Variables"""
    global DB_DSN, WS_URI, DB_REFRESH_INTERVAL, SOL_RESERVES_FULL, AGE_CALCULATION_OFFSET_MIN
    global TRADE_BUFFER_SECONDS, WHALE_THRESHOLD_SOL, DB_RETRY_DELAY, WS_RETRY_DELAY
    global WS_MAX_RETRY_DELAY, WS_PING_INTERVAL, WS_PING_TIMEOUT, WS_CONNECTION_TIMEOUT
    
    config_file = "/app/config/.env"
    if os.path.exists(config_file):
        try:
            print(f"📄 Lade Konfiguration aus {config_file}...", flush=True)
            with open(config_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        
                        # Überschreibe globale Variablen (nur wenn Wert nicht leer)
                        if value:
                            if key == "DB_DSN":
                                DB_DSN = value
                            elif key == "WS_URI":
                                WS_URI = value
                            elif key == "DB_REFRESH_INTERVAL" and value.isdigit():
                                DB_REFRESH_INTERVAL = int(value)
                            elif key == "SOL_RESERVES_FULL":
                                try:
                                    SOL_RESERVES_FULL = float(value)
                                except:
                                    pass
                            elif key == "AGE_CALCULATION_OFFSET_MIN" and value.isdigit():
                                AGE_CALCULATION_OFFSET_MIN = int(value)
                            elif key == "TRADE_BUFFER_SECONDS" and value.isdigit():
                                TRADE_BUFFER_SECONDS = int(value)
                            elif key == "WHALE_THRESHOLD_SOL":
                                try:
                                    WHALE_THRESHOLD_SOL = float(value)
                                except:
                                    pass
                            elif key == "DB_RETRY_DELAY" and value.isdigit():
                                DB_RETRY_DELAY = int(value)
                            elif key == "WS_RETRY_DELAY" and value.isdigit():
                                WS_RETRY_DELAY = int(value)
                            elif key == "WS_MAX_RETRY_DELAY" and value.isdigit():
                                WS_MAX_RETRY_DELAY = int(value)
                            elif key == "WS_PING_INTERVAL" and value.isdigit():
                                WS_PING_INTERVAL = int(value)
                            elif key == "WS_PING_TIMEOUT" and value.isdigit():
                                WS_PING_TIMEOUT = int(value)
                            elif key == "WS_CONNECTION_TIMEOUT" and value.isdigit():
                                WS_CONNECTION_TIMEOUT = int(value)
                            elif key == "HEALTH_PORT" and value.isdigit():
                                HEALTH_PORT = int(value)
            print(f"✅ Konfiguration aus {config_file} geladen", flush=True)
        except Exception as e:
            print(f"⚠️  Fehler beim Laden der Config-Datei {config_file}: {e}", flush=True)
    else:
        print(f"ℹ️  Config-Datei {config_file} nicht gefunden, verwende Environment Variables", flush=True)

# Lade Config beim Start (nach Environment Variables)
load_config_from_file()

# ZEITZONEN
GERMAN_TZ = ZoneInfo("Europe/Berlin")

# --- PROMETHEUS METRICS ---
trades_received = PromCounter("tracker_trades_received_total", "Anzahl empfangener Trades")
trades_processed = PromCounter("tracker_trades_processed_total", "Anzahl verarbeiteter Trades")
trades_from_buffer = PromCounter("tracker_trades_from_buffer_total", "Anzahl Trades aus Buffer verarbeitet")
metrics_saved = PromCounter("tracker_metrics_saved_total", "Anzahl gespeicherter Metriken")
coins_tracked = Gauge("tracker_coins_tracked", "Anzahl aktuell getrackter Coins")
coins_graduated = PromCounter("tracker_coins_graduated_total", "Anzahl graduierter Coins")
coins_finished = PromCounter("tracker_coins_finished_total", "Anzahl beendeter Coins")
phase_switches = PromCounter("tracker_phase_switches_total", "Anzahl Phasen-Wechsel")
db_errors = PromCounter("tracker_db_errors_total", "DB Fehler", ["type"])
ws_reconnects = PromCounter("tracker_ws_reconnects_total", "WebSocket Reconnects")
ws_connected = Gauge("tracker_ws_connected", "WebSocket Status (1=connected)")
db_connected = Gauge("tracker_db_connected", "DB Status (1=connected)")
uptime_seconds = Gauge("tracker_uptime_seconds", "Uptime in Sekunden")
last_trade_timestamp = Gauge("tracker_last_trade_timestamp", "Timestamp des letzten Trades")
connection_duration = Gauge("tracker_connection_duration_seconds", "Dauer der aktuellen Verbindung")
db_query_duration = Histogram("tracker_db_query_duration_seconds", "Dauer von DB-Queries")
flush_duration = Histogram("tracker_flush_duration_seconds", "Dauer von Metric-Flushes")
buffer_size = Gauge("tracker_trade_buffer_size", "Anzahl Trades im Buffer")
buffer_trades_total = PromCounter("tracker_buffer_trades_total", "Gesamt Trades im Buffer gespeichert")

# --- STATUS TRACKING ---
tracker_status = {
    "db_connected": False,
    "ws_connected": False,
    "last_error": None,
    "start_time": time.time(),
    "connection_start": None,
    "last_message_time": None,
    "reconnect_count": 0,
    "total_trades": 0,
    "total_metrics_saved": 0
}

# Globale Tracker-Instanz für Health-Check
_tracker_instance = None

async def metrics_handler(request):
    """Prometheus Metrics Endpoint"""
    uptime_seconds.set(time.time() - tracker_status["start_time"])
    if tracker_status["connection_start"]:
        connection_duration.set(time.time() - tracker_status["connection_start"])
    return web.Response(body=generate_latest(), content_type="text/plain; version=0.0.4", charset="utf-8")

async def health_check(request):
    """Health-Check Endpoint - muss immer funktionieren, auch während Initialisierung"""
    try:
        global _tracker_instance
        db_status = tracker_status.get("db_connected", False)
        ws_status = tracker_status.get("ws_connected", False)
        uptime = time.time() - tracker_status.get("start_time", time.time())
        last_msg = tracker_status.get("last_message_time")
        
        # DB-Tabellen-Prüfung (wenn DB verbunden ist)
        db_table_check = {
            "coin_metrics_exists": False,
            "coin_streams_exists": False,
            "discovered_coins_exists": False
        }
        
        if db_status and _tracker_instance and _tracker_instance.pool:
            try:
                async with _tracker_instance.pool.acquire() as conn:
                    # Prüfe coin_metrics Tabelle
                    coin_metrics_exists = await conn.fetchval("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_schema = 'public' 
                            AND table_name = 'coin_metrics'
                        )
                    """)
                    db_table_check["coin_metrics_exists"] = coin_metrics_exists
                    
                    # Prüfe coin_streams Tabelle
                    coin_streams_exists = await conn.fetchval("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_schema = 'public' 
                            AND table_name = 'coin_streams'
                        )
                    """)
                    db_table_check["coin_streams_exists"] = coin_streams_exists
                    
                    # Prüfe discovered_coins Tabelle
                    discovered_coins_exists = await conn.fetchval("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_schema = 'public' 
                            AND table_name = 'discovered_coins'
                        )
                    """)
                    db_table_check["discovered_coins_exists"] = discovered_coins_exists
            except Exception as e:
                # Tabellen-Prüfung fehlgeschlagen - ignorieren
                pass
        
        # Buffer-Statistiken berechnen (sicherheitshalber mit try-except)
        buffer_stats = {
            "total_trades_in_buffer": 0,
            "coins_with_buffer": 0,
            "buffer_details": {}
        }
        
        # Hole Tracker-Instanz (wenn verfügbar)
        try:
            if _tracker_instance and hasattr(_tracker_instance, 'trade_buffer'):
                buffer_stats["total_trades_in_buffer"] = sum(len(trades) for trades in _tracker_instance.trade_buffer.values())
                buffer_stats["coins_with_buffer"] = len(_tracker_instance.trade_buffer)
                
                # Top 10 Coins mit meisten Trades im Buffer
                coin_buffer_counts = [(mint, len(trades)) for mint, trades in _tracker_instance.trade_buffer.items()]
                coin_buffer_counts.sort(key=lambda x: x[1], reverse=True)
                
                buffer_stats["buffer_details"] = {
                    coin[:12] + "..." if len(coin) > 12 else coin: count 
                    for coin, count in coin_buffer_counts[:10]
                }
        except Exception as e:
            # Buffer-Statistiken sind optional - Fehler ignorieren
            pass
        
        health_data = {
            "status": "healthy" if (db_status and ws_status) else "degraded",
            "db_connected": db_status,
            "db_tables": db_table_check,
            "ws_connected": ws_status,
            "uptime_seconds": int(uptime),
            "total_trades": tracker_status.get("total_trades", 0),
            "total_metrics_saved": tracker_status.get("total_metrics_saved", 0),
            "last_message_ago": int(time.time() - last_msg) if last_msg else None,
            "reconnect_count": tracker_status.get("reconnect_count", 0),
            "last_error": tracker_status.get("last_error"),
            "buffer_stats": buffer_stats
        }
        
        # HTTP Status Code: 200 für healthy/degraded, 503 nur bei kritischen Fehlern
        # WICHTIG: Coolify erwartet 200 für "healthy" Status
        if db_status and ws_status:
            status_code = 200  # Healthy
        elif db_status or ws_status:
            status_code = 200  # Degraded (aber noch funktionsfähig) - Coolify sollte "Running" zeigen
        else:
            status_code = 503  # Service Unavailable (beide Verbindungen down)
        
        # Coolify-spezifische Header für bessere Erkennung
        response = web.json_response(health_data, status=status_code)
        response.headers['X-Health-Status'] = health_data['status']
        response.headers['X-Service-Status'] = 'running' if status_code == 200 else 'unavailable'
        return response
    except Exception as e:
        # Fallback: Immer einen gültigen Response zurückgeben
        error_data = {
            "status": "error",
            "error": str(e),
            "uptime_seconds": int(time.time() - tracker_status.get("start_time", time.time()))
        }
        return web.json_response(error_data, status=500)

async def reload_config_handler(request):
    """Lädt die Konfiguration neu (ohne Neustart)"""
    try:
        # Verwende die gleiche Funktion wie beim Start
        load_config_from_file()
        
        print(f"🔄 Konfiguration neu geladen:", flush=True)
        print(f"  - DB_REFRESH_INTERVAL: {DB_REFRESH_INTERVAL}s", flush=True)
        print(f"  - TRADE_BUFFER_SECONDS: {TRADE_BUFFER_SECONDS}s", flush=True)
        print(f"  - WHALE_THRESHOLD_SOL: {WHALE_THRESHOLD_SOL}", flush=True)
        
        return web.json_response({
            "status": "success",
            "message": "Konfiguration wurde neu geladen",
            "config": {
                "DB_REFRESH_INTERVAL": DB_REFRESH_INTERVAL,
                "TRADE_BUFFER_SECONDS": TRADE_BUFFER_SECONDS,
                "WHALE_THRESHOLD_SOL": WHALE_THRESHOLD_SOL
            }
        })
    except Exception as e:
        return web.json_response({
            "status": "error",
            "message": str(e)
        }, status=500)

async def start_health_server():
    """Startet den Health-Check Server - muss sofort verfügbar sein"""
    app = web.Application()
    app.add_routes([
        web.get("/health", health_check),
        web.get("/metrics", metrics_handler),
        web.post("/reload-config", reload_config_handler),  # Reload-Endpoint
        # Coolify-spezifischer Endpoint (manche Versionen erwarten /)
        web.get("/", health_check)
    ])
    
    # CORS-Header für Coolify (falls nötig)
    async def cors_middleware(app, handler):
        async def middleware_handler(request):
            response = await handler(request)
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = '*'
            return response
        return middleware_handler
    
    app.middlewares.append(cors_middleware)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HEALTH_PORT)
    await site.start()
    print(f"🏥 Health-Check Server läuft auf Port {HEALTH_PORT}", flush=True)
    print(f"📊 Prometheus Metrics auf http://localhost:{HEALTH_PORT}/metrics", flush=True)
    print(f"✅ Health-Endpoint verfügbar: http://0.0.0.0:{HEALTH_PORT}/health", flush=True)
    print(f"🔄 Reload-Config Endpoint: http://0.0.0.0:{HEALTH_PORT}/reload-config", flush=True)

class Tracker:
    def __init__(self):
        self.pool = None
        self.phases_config = {}
        self.watchlist = {}
        self.subscribed_mints = set()
        self.sorted_phase_ids = []
        # {TRADE_BUFFER_SECONDS}-Sekunden-Buffer für alle empfangenen Trades (Standard: 180s = 3 Minuten)
        # Struktur: {mint: [(timestamp, trade_data), ...]}
        self.trade_buffer = {}
        self.last_buffer_cleanup = time.time()
        # Track welche Coins bereits über subscribeNewToken abonniert wurden
        self.early_subscribed_mints = set()

    async def init_db_connection(self):
        while True:
            try:
                if self.pool:
                    await self.pool.close()
                self.pool = await asyncpg.create_pool(DB_DSN, min_size=1, max_size=10)
                
                # Automatische Schema-Migration beim Start
                print("🔍 Prüfe und aktualisiere Datenbank-Schema...", flush=True)
                schema_ok = await check_and_create_schema(self.pool)
                if not schema_ok:
                    print("⚠️  Schema-Check fehlgeschlagen, aber Verbindung funktioniert", flush=True)
                
                rows = await self.pool.fetch("SELECT * FROM ref_coin_phases ORDER BY id ASC")
                self.phases_config = {}
                for row in rows:
                    self.phases_config[row["id"]] = {
                        "interval": row["interval_seconds"],
                        "max_age": row["max_age_minutes"],
                        "name": row["name"]
                    }
                self.sorted_phase_ids = sorted(self.phases_config.keys())
                print(f"✅ DB verbunden. Geladene Phasen: {self.sorted_phase_ids}", flush=True)
                tracker_status["db_connected"] = True
                tracker_status["last_error"] = None
                db_connected.set(1)
                return
            except Exception as e:
                tracker_status["db_connected"] = False
                tracker_status["last_error"] = f"db_error: {str(e)[:100]}"
                db_connected.set(0)
                db_errors.labels(type="connection").inc()
                print(f"❌ DB Verbindungsfehler: {e}", flush=True)
                print(f"⏳ Retry in {DB_RETRY_DELAY}s...", flush=True)
                await asyncio.sleep(DB_RETRY_DELAY)

    async def get_active_streams(self):
        try:
            with db_query_duration.time():
                # Zuerst: Repariere fehlende Streams (sicherheitshalber)
                try:
                    await self.pool.execute("SELECT repair_missing_streams()")
                except Exception as e:
                    # Funktion existiert möglicherweise noch nicht - ignorieren
                    pass
                
                # Dann: Hole aktive Streams
                sql = """
                    SELECT cs.token_address, cs.current_phase_id, dc.token_created_at, cs.started_at, dc.trader_public_key
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
                    results[mint] = {
                        "phase_id": row["current_phase_id"],
                        "created_at": created_at,
                        "started_at": started_at or created_at,
                        "creator_address": row.get("trader_public_key")  # Dev-Wallet für Rug-Pull-Erkennung
                    }
                
                # Prüfe auf Lücken (nur alle 60 Sekunden, um Performance zu schonen)
                if not hasattr(self, '_last_gap_check') or (time.time() - self._last_gap_check) > 60:
                    try:
                        gap_result = await self.pool.fetchrow("SELECT * FROM check_stream_gaps()")
                        if gap_result and gap_result["missing_streams_count"] > 0:
                            print(f"⚠️ WARNUNG: {gap_result['missing_streams_count']} Coins ohne Stream gefunden!", flush=True)
                            if gap_result["coins_without_streams"]:
                                print(f"   Betroffene Coins: {', '.join(gap_result['coins_without_streams'][:5])}...", flush=True)
                    except Exception as e:
                        # Funktion existiert möglicherweise noch nicht - ignorieren
                        pass
                    self._last_gap_check = time.time()
                
                return results
        except Exception as e:
            print(f"⚠️ DB Query Error: {e}", flush=True)
            tracker_status["db_connected"] = False
            db_connected.set(0)
            db_errors.labels(type="query").inc()
            raise

    async def switch_phase(self, mint, old_phase, new_phase):
        try:
            print(f"🆙 UPGRADE: {mint} Phase {old_phase} -> {new_phase}", flush=True)
            async with self.pool.acquire() as conn:
                await conn.execute("UPDATE coin_streams SET current_phase_id = $1 WHERE token_address = $2", new_phase, mint)
            phase_switches.inc()
        except Exception as e:
            print(f"⚠️ Phase Switch Error: {e}", flush=True)
            tracker_status["db_connected"] = False
            db_connected.set(0)
            db_errors.labels(type="update").inc()

    async def stop_tracking(self, mint, is_graduation=False):
        try:
            if is_graduation:
                print(f"🎉 GRADUATION: {mint} geht zu Raydium! Tracking beendet.", flush=True)
                final_phase = 100
                graduated_flag = True
                coins_graduated.inc()
            else:
                print(f"🏁 FINISHED: {mint} Lifecycle beendet.", flush=True)
                final_phase = 99
                graduated_flag = False
                coins_finished.inc()
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE coin_streams
                    SET is_active = FALSE,
                        current_phase_id = $2,
                        is_graduated = $3
                    WHERE token_address = $1
                """, mint, final_phase, graduated_flag)
        except Exception as e:
            print(f"⚠️ Stop Tracking Error: {e}", flush=True)
            tracker_status["db_connected"] = False
            db_connected.set(0)
            db_errors.labels(type="update").inc()
        finally:
            if mint in self.watchlist: del self.watchlist[mint]
            if mint in self.subscribed_mints: self.subscribed_mints.remove(mint)
            coins_tracked.set(len(self.watchlist))

    def get_empty_buffer(self):
        return {
            "open": None, "high": -1, "low": float("inf"), "close": 0,
            "vol": 0, "vol_buy": 0, "vol_sell": 0, "buys": 0, "sells": 0,
            "micro_trades": 0, "max_buy": 0, "max_sell": 0,
            "wallets": set(), "v_sol": 0, "mcap": 0,
            # NEU: Whale-Tracking
            "whale_buy_vol": 0,
            "whale_sell_vol": 0,
            "whale_buys": 0,
            "whale_sells": 0,
            # NEU: Dev-Tracking (Rug-Pull-Erkennung)
            "dev_sold_amount": 0
        }

    async def run_new_token_listener(self, subscribe_queue):
        """Zweiter WebSocket-Stream: Hört auf subscribeNewToken und abonniert neue Coins sofort"""
        reconnect_count = 0
        
        while True:
            try:
                print(f"🔌 Verbinde NewToken-Listener... (Versuch #{reconnect_count + 1})", flush=True)
                
                async with websockets.connect(
                    WS_URI,
                    ping_interval=WS_PING_INTERVAL,
                    ping_timeout=WS_PING_TIMEOUT,
                    close_timeout=10,
                    max_size=2**23,
                    compression=None
                ) as ws_new_token:
                    print("✅ NewToken-Listener verbunden! Abonniere subscribeNewToken...", flush=True)
                    
                    # Abonniere neue Coins
                    await ws_new_token.send(json.dumps({"method": "subscribeNewToken"}))
                    print("📡 subscribeNewToken aktiv - warte auf neue Coins...", flush=True)
                    
                    reconnect_count = 0
                    
                    while True:
                        try:
                            msg = await asyncio.wait_for(ws_new_token.recv(), timeout=1.0)
                            data = json.loads(msg)
                            
                            # Prüfe ob es ein neuer Coin ist (create Event)
                            if data.get("txType") == "create" and "mint" in data:
                                mint = data["mint"]
                                
                                # Prüfe ob Coin bereits abonniert wurde
                                if mint not in self.early_subscribed_mints:
                                    print(f"🆕 Neuer Coin erkannt: {mint[:8]}... - abonniere SOFORT für {TRADE_BUFFER_SECONDS}s Buffer!", flush=True)
                                    
                                    # Sende Abonnement-Anfrage über Queue an Trade-WebSocket
                                    await subscribe_queue.put(mint)
                                    self.early_subscribed_mints.add(mint)
                                    print(f"✅ {mint[:8]}... sofort abonniert - Trades werden {TRADE_BUFFER_SECONDS}s ({TRADE_BUFFER_SECONDS//60} Minuten) im Buffer gespeichert", flush=True)
                            
                        except asyncio.TimeoutError:
                            # Timeout ist okay, wir warten weiter
                            continue
                        
                        except websockets.exceptions.ConnectionClosed as e:
                            print(f"🔌 NewToken-Listener Verbindung geschlossen: {e}", flush=True)
                            break
                        
                        except json.JSONDecodeError as e:
                            print(f"⚠️ JSON Fehler (NewToken): {e}", flush=True)
                            continue
                        
                        except Exception as e:
                            print(f"⚠️ NewToken-Listener Error: {e}", flush=True)
                            break
            
            except websockets.exceptions.WebSocketException as e:
                print(f"❌ NewToken-Listener WebSocket Exception: {e}", flush=True)
                reconnect_count += 1
            
            except Exception as e:
                print(f"❌ NewToken-Listener unerwarteter Fehler: {e}", flush=True)
                reconnect_count += 1
            
            delay = min(WS_RETRY_DELAY * (1 + reconnect_count * 0.5), WS_MAX_RETRY_DELAY)
            print(f"⏳ NewToken-Listener Reconnect in {delay:.1f}s...", flush=True)
            await asyncio.sleep(delay)

    async def run(self):
        await self.init_db_connection()
        reconnect_count = 0
        
        while True:
            try:
                print(f"🔌 Verbinde zu WebSocket (Trade-Stream)... (Versuch #{reconnect_count + 1})", flush=True)
                
                async with websockets.connect(
                    WS_URI,
                    ping_interval=WS_PING_INTERVAL,
                    ping_timeout=WS_PING_TIMEOUT,
                    close_timeout=10,
                    max_size=2**23,
                    compression=None
                ) as ws:
                    tracker_status["ws_connected"] = True
                    tracker_status["connection_start"] = time.time()
                    tracker_status["last_error"] = None
                    ws_connected.set(1)
                    reconnect_count = 0
                    tracker_status["reconnect_count"] = 0
                    
                    print("✅ Trade-WebSocket verbunden! Tracker läuft...", flush=True)
                    
                    # PRE-SUBSCRIPTION: Alle aktiven Coins beim Start abonnieren
                    print("📡 Pre-Subscription: Lade alle aktiven Coins...", flush=True)
                    try:
                        initial_streams = await self.get_active_streams()
                        if initial_streams:
                            initial_mints = list(initial_streams.keys())
                            print(f"📡 Abonniere {len(initial_mints)} aktive Coins beim Start...", flush=True)
                            await ws.send(json.dumps({"method": "subscribeTokenTrade", "keys": initial_mints}))
                            
                            # Initialisiere Watchlist für alle Coins
                            now_ts = time.time()
                            for mint in initial_mints:
                                p_id = initial_streams[mint]["phase_id"]
                                if p_id not in self.phases_config:
                                    p_id = self.sorted_phase_ids[0] if self.sorted_phase_ids else 1
                                interval = self.phases_config[p_id]["interval"]
                                self.watchlist[mint] = {
                                    "meta": initial_streams[mint],
                                    "buffer": self.get_empty_buffer(),
                                    "next_flush": now_ts + interval,
                                    "interval": interval
                                }
                                self.subscribed_mints.add(mint)
                                self.early_subscribed_mints.add(mint)  # Bereits abonniert (für Buffer-Verarbeitung wichtig)
                            
                            print(f"✅ {len(initial_mints)} Coins vorab abonniert und zur Watchlist hinzugefügt", flush=True)
                            coins_tracked.set(len(self.watchlist))
                        else:
                            print("ℹ️  Keine aktiven Coins beim Start gefunden", flush=True)
                    except Exception as e:
                        print(f"⚠️ Pre-Subscription Fehler: {e}. Weiter ohne Pre-Subscription...", flush=True)
                    
                    # STARTE ZWEITEN STREAM: NewToken-Listener im Hintergrund
                    print("🚀 Starte NewToken-Listener (zweiter Stream für subscribeNewToken)...", flush=True)
                    subscribe_queue = asyncio.Queue()
                    new_token_task = asyncio.create_task(self.run_new_token_listener(subscribe_queue))
                    
                    last_refresh = 0
                    last_message_time = time.time()
                    
                    while True:
                        now_ts = time.time()
                        
                        # Prüfe Queue für neue Abonnements vom NewToken-Listener
                        try:
                            while not subscribe_queue.empty():
                                mint = await asyncio.wait_for(subscribe_queue.get(), timeout=0.1)
                                # Abonniere Coin sofort im Trade-WebSocket
                                await ws.send(json.dumps({"method": "subscribeTokenTrade", "keys": [mint]}))
                                print(f"📡 {mint[:8]}... über NewToken-Listener abonniert", flush=True)
                        except asyncio.TimeoutError:
                            pass
                        except Exception as e:
                            print(f"⚠️ Queue-Verarbeitung Fehler: {e}", flush=True)
                        
                        if now_ts - last_refresh > DB_REFRESH_INTERVAL:
                            try:
                                db_streams = await self.get_active_streams()
                                current_set = set(db_streams.keys())
                                to_remove = self.subscribed_mints - current_set
                                
                                if to_remove:
                                    for mint in to_remove:
                                        if mint in self.watchlist: del self.watchlist[mint]
                                        self.subscribed_mints.remove(mint)
                                
                                to_add = current_set - self.subscribed_mints
                                if to_add:
                                    print(f"📡 {len(to_add)} Coins in coin_streams aktiviert - starte Tracking...", flush=True)
                                    
                                    # Prüfe ob Coins bereits über NewToken-Listener abonniert wurden
                                    to_subscribe_now = []
                                    for mint in to_add:
                                        if mint not in self.early_subscribed_mints:
                                            # Coin wurde noch nicht abonniert - abonniere jetzt
                                            to_subscribe_now.append(mint)
                                            self.early_subscribed_mints.add(mint)
                                    
                                    if to_subscribe_now:
                                        print(f"📡 {len(to_subscribe_now)} Coins wurden noch nicht abonniert - abonniere jetzt...", flush=True)
                                        await ws.send(json.dumps({"method": "subscribeTokenTrade", "keys": to_subscribe_now}))
                                    
                                    # Verarbeite verpasste Trades aus dem Buffer für jeden neuen Coin
                                    total_buffer_trades = 0
                                    for mint in to_add:
                                        p_id = db_streams[mint]["phase_id"]
                                        if p_id not in self.phases_config:
                                            p_id = self.sorted_phase_ids[0] if self.sorted_phase_ids else 1
                                        interval = self.phases_config[p_id]["interval"]
                                        
                                        # Initialisiere Watchlist-Eintrag
                                        self.watchlist[mint] = {
                                            "meta": db_streams[mint],
                                            "buffer": self.get_empty_buffer(),
                                            "next_flush": now_ts + interval,
                                            "interval": interval
                                        }
                                        self.subscribed_mints.add(mint)
                                        
                                        # RÜCKWIRKENDE BERECHNUNG: Verarbeite verpasste Trades aus dem Buffer
                                        created_at = db_streams[mint]["created_at"]
                                        started_at = db_streams[mint]["started_at"]
                                        
                                        # Prüfe ob Coin bereits abonniert war (entweder über NewToken-Listener oder hat Trades im Buffer)
                                        # Wenn Coin Trades im Buffer hat, bedeutet das dass er bereits abonniert war
                                        has_buffer = mint in self.trade_buffer
                                        is_early_subscribed = mint in self.early_subscribed_mints
                                        buffer_size = len(self.trade_buffer.get(mint, []))
                                        
                                        # Prüfe ob Coin im trade_buffer ist (auch mit Teilstring-Match für ähnliche Adressen)
                                        buffer_keys_match = [k for k in self.trade_buffer.keys() if k[:8] == mint[:8]]
                                        
                                        if buffer_size > 0 or has_buffer:
                                            print(f"🔍 {mint[:8]}...: early_subscribed={is_early_subscribed}, has_buffer={has_buffer}, buffer_size={buffer_size}", flush=True)
                                        
                                        # Prüfe auch ob ein ähnlicher Coin im Buffer ist (für den Fall dass Adressen leicht abweichen)
                                        buffer_match = None
                                        if not has_buffer and buffer_keys_match:
                                            # Versuche den ersten passenden Coin zu verwenden
                                            buffer_match = buffer_keys_match[0]
                                            print(f"🔄 {mint[:8]}...: Verwende ähnlichen Coin aus Buffer: {buffer_match[:12]}...", flush=True)
                                            has_buffer = True  # Verwende den ähnlichen Coin
                                        
                                        if is_early_subscribed or has_buffer:
                                            # Coin wurde bereits abonniert - verarbeite Buffer rückwirkend
                                            # Verwende buffer_match falls vorhanden, sonst mint
                                            buffer_mint = buffer_match if buffer_match else mint
                                            buffer_trades = self.process_trades_from_buffer(buffer_mint, created_at, started_at)
                                            total_buffer_trades += buffer_trades
                                            if buffer_trades > 0:
                                                print(f"✅ {mint[:8]}...: {buffer_trades} Trades aus Buffer verarbeitet", flush=True)
                                            elif has_buffer:
                                                actual_buffer_size = len(self.trade_buffer.get(buffer_mint, []))
                                                print(f"ℹ️  {mint[:8]}...: Hat {actual_buffer_size} Trades im Buffer, aber keine wurden verarbeitet (Zeitfenster-Problem?)", flush=True)
                                    
                                    if total_buffer_trades > 0:
                                        print(f"🔄 RÜCKWIRKEND: {total_buffer_trades} verpasste Trades aus {TRADE_BUFFER_SECONDS}s-Buffer ({TRADE_BUFFER_SECONDS//60} Minuten) verarbeitet", flush=True)
                                    
                                    print(f"✅ {len(to_add)} Coins zum Tracking hinzugefügt. Gesamt: {len(self.watchlist)}", flush=True)
                                
                                tracker_status["db_connected"] = True
                                db_connected.set(1)
                                coins_tracked.set(len(self.watchlist))
                                last_refresh = now_ts
                            except Exception as e:
                                print(f"⚠️ DB Sync Error: {e}. Weiter ohne DB-Update...", flush=True)
                                tracker_status["db_connected"] = False
                                db_connected.set(0)
                                last_refresh = now_ts
                        
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                            last_message_time = time.time()
                            tracker_status["last_message_time"] = last_message_time
                            
                            data = json.loads(msg)
                            trades_received.inc()
                            
                            # Alle Trades (buy/sell) zum Buffer hinzufügen
                            if "txType" in data and data.get("txType") in ["buy", "sell"]:
                                self.add_trade_to_buffer(data)
                                
                                # Wenn Coin bereits in Watchlist: Sofort verarbeiten
                                if data["mint"] in self.watchlist:
                                    self.process_trade(data)
                                    trades_processed.inc()
                                    tracker_status["total_trades"] += 1
                                    last_trade_timestamp.set(time.time())
                                    
                                    # Log alle 100 Trades einen Status
                                    if tracker_status["total_trades"] % 100 == 0:
                                        print(f"📈 {tracker_status['total_trades']} Trades verarbeitet, {len(self.watchlist)} Coins im Tracking", flush=True)
                        
                        except asyncio.TimeoutError:
                            if time.time() - last_message_time > WS_CONNECTION_TIMEOUT:
                                print(f"⚠️ Keine Nachrichten seit {WS_CONNECTION_TIMEOUT}s - Reconnect", flush=True)
                                raise websockets.exceptions.ConnectionClosed(1006, "Timeout")
                        
                        except websockets.exceptions.ConnectionClosed as e:
                            print(f"🔌 Trade-WebSocket Verbindung geschlossen: {e}", flush=True)
                            tracker_status["ws_connected"] = False
                            tracker_status["last_error"] = f"ws_closed: {str(e)[:100]}"
                            ws_connected.set(0)
                            # Stoppe NewToken-Listener Task
                            if 'new_token_task' in locals():
                                new_token_task.cancel()
                            break
                        
                        except json.JSONDecodeError as e:
                            print(f"⚠️ JSON Fehler: {e}", flush=True)
                            continue
                        
                        except Exception as e:
                            print(f"⚠️ WS Receive Error: {e}", flush=True)
                            tracker_status["last_error"] = f"ws_error: {str(e)[:100]}"
                            break
                        
                        # Buffer-Cleanup alle 10 Sekunden
                        if now_ts - self.last_buffer_cleanup > 10:
                            removed = self.cleanup_old_trades_from_buffer(now_ts)
                            if removed > 0:
                                print(f"🧹 Buffer-Cleanup: {removed} alte Trades entfernt", flush=True)
                            self.last_buffer_cleanup = now_ts
                        
                        await self.check_lifecycle_and_flush(now_ts)
            
            except websockets.exceptions.WebSocketException as e:
                tracker_status["ws_connected"] = False
                tracker_status["last_error"] = f"ws_exception: {str(e)[:100]}"
                ws_connected.set(0)
                ws_reconnects.inc()
                print(f"❌ WebSocket Exception: {e}", flush=True)
                reconnect_count += 1
                tracker_status["reconnect_count"] = reconnect_count
            
            except Exception as e:
                tracker_status["ws_connected"] = False
                tracker_status["last_error"] = f"unexpected: {str(e)[:100]}"
                ws_connected.set(0)
                ws_reconnects.inc()
                print(f"❌ Unerwarteter Fehler: {e}", flush=True)
                reconnect_count += 1
                tracker_status["reconnect_count"] = reconnect_count
            
            delay = min(WS_RETRY_DELAY * (1 + reconnect_count * 0.5), WS_MAX_RETRY_DELAY)
            print(f"⏳ Reconnect in {delay:.1f}s...", flush=True)
            await asyncio.sleep(delay)
            
            if not tracker_status["db_connected"]:
                print("🔄 DB auch getrennt, versuche Reconnect...", flush=True)
                await self.init_db_connection()

    def add_trade_to_buffer(self, data):
        f"""Fügt einen Trade zum {TRADE_BUFFER_SECONDS}-Sekunden-Buffer hinzu"""
        mint = data.get("mint")
        if not mint:
            return
        
        if mint not in self.trade_buffer:
            self.trade_buffer[mint] = []
        
        trade_entry = (time.time(), data)
        self.trade_buffer[mint].append(trade_entry)
        buffer_trades_total.inc()
        
        # Begrenze Buffer-Größe pro Coin (max 5000 Trades für 3 Minuten = ~27 Trades/Sekunde)
        if len(self.trade_buffer[mint]) > 5000:
            self.trade_buffer[mint] = self.trade_buffer[mint][-5000:]
    
    def cleanup_old_trades_from_buffer(self, now_ts):
        """Entfernt Trades aus dem Buffer, die älter als TRADE_BUFFER_SECONDS sind"""
        cutoff_time = now_ts - TRADE_BUFFER_SECONDS
        total_removed = 0
        
        for mint in list(self.trade_buffer.keys()):
            original_len = len(self.trade_buffer[mint])
            self.trade_buffer[mint] = [
                (ts, data) for ts, data in self.trade_buffer[mint]
                if ts > cutoff_time
            ]
            removed = original_len - len(self.trade_buffer[mint])
            total_removed += removed
            
            # Entferne leere Einträge
            if not self.trade_buffer[mint]:
                del self.trade_buffer[mint]
        
        # Update Prometheus Metric
        total_buffer_size = sum(len(trades) for trades in self.trade_buffer.values())
        buffer_size.set(total_buffer_size)
        
        return total_removed
    
    def process_trades_from_buffer(self, mint, created_at, started_at):
        """Verarbeitet verpasste Trades aus dem Buffer für einen neu aktivierten Coin (rückwirkend)"""
        if mint not in self.trade_buffer:
            print(f"ℹ️  {mint[:8]}...: Keine Trades im Buffer", flush=True)
            return 0
        
        # Konvertiere Timestamps zu Unix-Timestamp
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        
        created_ts = created_at.timestamp()
        started_ts = started_at.timestamp()
        now_ts = time.time()
        
        # Finde alle Trades im relevanten Zeitraum
        # Zeitraum: created_at bis jetzt (alle Trades die zwischen Coin-Erstellung und Aktivierung passiert sind)
        # Aber maximal TRADE_BUFFER_SECONDS (180 Sekunden = 3 Minuten) zurück
        # WICHTIG: Wenn started_at gerade gesetzt wurde (NOW()), dann sollten ALLE Trades im Buffer verarbeitet werden
        # die zwischen created_at und jetzt passiert sind
        cutoff_ts = max(created_ts, now_ts - TRADE_BUFFER_SECONDS)
        # end_ts sollte jetzt sein, damit alle Trades bis zur Aktivierung verarbeitet werden
        end_ts = now_ts
        
        # Nur detailliertes Logging wenn Buffer vorhanden ist
        if len(self.trade_buffer[mint]) > 0:
            print(f"🔍 {mint[:8]}...: Prüfe Buffer - created_ts={created_ts:.1f}, started_ts={started_ts:.1f}, now_ts={now_ts:.1f}, cutoff_ts={cutoff_ts:.1f}, end_ts={end_ts:.1f}", flush=True)
            print(f"🔍 {mint[:8]}...: Buffer hat {len(self.trade_buffer[mint])} Trades", flush=True)
        
        relevant_trades = []
        for trade_ts, trade_data in self.trade_buffer[mint]:
            # Trade muss im relevanten Zeitraum liegen
            if cutoff_ts <= trade_ts <= end_ts:
                relevant_trades.append((trade_ts, trade_data))
        
        if len(relevant_trades) > 0:
            print(f"🔍 {mint[:8]}...: {len(relevant_trades)} relevante Trades gefunden für rückwirkende Verarbeitung", flush=True)
        
        # Sortiere nach Timestamp (älteste zuerst) für chronologische Verarbeitung
        relevant_trades.sort(key=lambda x: x[0])
        
        # Verarbeite alle relevanten Trades chronologisch
        processed_count = 0
        for trade_ts, trade_data in relevant_trades:
            if mint in self.watchlist:
                self.process_trade(trade_data)
                processed_count += 1
                trades_from_buffer.inc()
            else:
                print(f"⚠️  {mint[:8]}...: Trade kann nicht verarbeitet werden - Coin nicht in Watchlist", flush=True)
        
        if processed_count > 0:
            mint_short = mint[:8] + "..." if len(mint) > 8 else mint
            time_range = f"{int(end_ts - cutoff_ts)}s"
            print(f"🔄 Buffer: {processed_count} rückwirkende Trades für {mint_short} verarbeitet (Zeitraum: {time_range})", flush=True)
        
        return processed_count
    
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
        if buf["open"] is None: buf["open"] = price
        buf["close"] = price
        buf["high"] = max(buf["high"], price)
        buf["low"] = min(buf["low"], price)
        buf["vol"] += sol
        if is_buy:
            buf["buys"] += 1
            buf["vol_buy"] += sol
            buf["max_buy"] = max(buf["max_buy"], sol)
            # NEU: Whale-Tracking
            if sol >= WHALE_THRESHOLD_SOL:
                buf["whale_buy_vol"] += sol
                buf["whale_buys"] += 1
        else:
            buf["sells"] += 1
            buf["vol_sell"] += sol
            buf["max_sell"] = max(buf["max_sell"], sol)
            # NEU: Whale-Tracking
            if sol >= WHALE_THRESHOLD_SOL:
                buf["whale_sell_vol"] += sol
                buf["whale_sells"] += 1
            # KRITISCH: Dev-Tracking (Rug-Pull-Erkennung)
            creator_address = entry["meta"].get("creator_address")
            if creator_address and trader_key and trader_key == creator_address:
                buf["dev_sold_amount"] += sol
        if sol < 0.01: buf["micro_trades"] += 1
        buf["wallets"].add(trader_key)
        buf["v_sol"] = float(data["vSolInBondingCurve"])
        buf["mcap"] = price * 1_000_000_000

    def calculate_advanced_metrics(self, buf):
        """
        Berechnet erweiterte Metriken aus dem Buffer
        Alle Werte basieren auf echten Trade-Daten (keine erfundenen Zahlen)
        """
        # 1. Netto-Volumen (Delta): buy_volume - sell_volume
        net_volume = buf["vol_buy"] - buf["vol_sell"]
        
        # 2. Volatilität: ((high - low) / open) * 100
        if buf["open"] and buf["open"] > 0:
            price_range = buf["high"] - buf["low"]
            volatility = (price_range / buf["open"]) * 100
        else:
            volatility = 0.0
        
        # 3. Durchschnittliche Trade-Größe: volume / (num_buys + num_sells)
        total_trades = buf["buys"] + buf["sells"]
        if total_trades > 0:
            avg_trade_size = buf["vol"] / total_trades
        else:
            avg_trade_size = 0.0
        
        # 4. Whale-Metriken (bereits im Buffer gesammelt)
        whale_buy_vol = buf["whale_buy_vol"]
        whale_sell_vol = buf["whale_sell_vol"]
        num_whale_buys = buf["whale_buys"]
        num_whale_sells = buf["whale_sells"]
        
        # 5. Buy Pressure Ratio: buy_volume / (buy_volume + sell_volume)
        total_volume = buf["vol_buy"] + buf["vol_sell"]
        if total_volume > 0:
            buy_pressure_ratio = buf["vol_buy"] / total_volume
        else:
            buy_pressure_ratio = 0.0
        
        # 6. Unique Signer Ratio: unique_wallets / (num_buys + num_sells)
        total_trades = buf["buys"] + buf["sells"]
        if total_trades > 0:
            unique_signer_ratio = len(buf["wallets"]) / total_trades
        else:
            unique_signer_ratio = 0.0
        
        return {
            "net_volume_sol": net_volume,
            "volatility_pct": volatility,
            "avg_trade_size_sol": avg_trade_size,
            "whale_buy_volume_sol": whale_buy_vol,
            "whale_sell_volume_sol": whale_sell_vol,
            "num_whale_buys": num_whale_buys,
            "num_whale_sells": num_whale_sells,
            "buy_pressure_ratio": buy_pressure_ratio,
            "unique_signer_ratio": unique_signer_ratio
        }

    async def check_lifecycle_and_flush(self, now_ts):
        batch_data = []
        phases_in_batch = []
        now_utc = datetime.now(timezone.utc)
        now_berlin = datetime.now(GERMAN_TZ)
        
        for mint, entry in list(self.watchlist.items()):
            buf = entry["buffer"]
            current_bonding_pct = (buf["v_sol"] / SOL_RESERVES_FULL) * 100
            if current_bonding_pct >= 99.5:
                await self.stop_tracking(mint, is_graduation=True)
                continue
            created_at = entry["meta"]["created_at"]
            current_pid = entry["meta"]["phase_id"]
            diff = now_utc - created_at
            age_minutes = (diff.total_seconds() / 60) - AGE_CALCULATION_OFFSET_MIN
            if age_minutes < 0: age_minutes = 0
            phase_cfg = self.phases_config.get(current_pid)
            if phase_cfg and age_minutes > phase_cfg["max_age"]:
                next_pid = None
                for pid in self.sorted_phase_ids:
                    if pid > current_pid:
                        next_pid = pid
                        break
                if next_pid is None or next_pid >= 99:
                    await self.stop_tracking(mint, is_graduation=False)
                    continue
                else:
                    await self.switch_phase(mint, current_pid, next_pid)
                    entry["meta"]["phase_id"] = next_pid
                    new_interval = self.phases_config[next_pid]["interval"]
                    entry["interval"] = new_interval
                    entry["next_flush"] = now_ts + new_interval
            if now_ts >= entry["next_flush"]:
                if buf["vol"] > 0:
                    is_koth = buf["mcap"] > 30000
                    
                    # NEU: Erweiterte Metriken berechnen
                    advanced_metrics = self.calculate_advanced_metrics(buf)
                    
                    batch_data.append((
                        mint, now_berlin, entry["meta"]["phase_id"],
                        buf["open"], buf["high"], buf["low"], buf["close"], buf["mcap"],
                        current_bonding_pct, buf["v_sol"], is_koth,
                        buf["vol"], buf["vol_buy"], buf["vol_sell"],
                        buf["buys"], buf["sells"], len(buf["wallets"]), buf["micro_trades"],
                        buf["dev_sold_amount"], buf["max_buy"], buf["max_sell"],  # KRITISCH: dev_sold_amount jetzt implementiert
                        # NEU: Erweiterte Metriken
                        advanced_metrics["net_volume_sol"],
                        advanced_metrics["volatility_pct"],
                        advanced_metrics["avg_trade_size_sol"],
                        advanced_metrics["whale_buy_volume_sol"],
                        advanced_metrics["whale_sell_volume_sol"],
                        advanced_metrics["num_whale_buys"],
                        advanced_metrics["num_whale_sells"],
                        # NEU: Ratio-Metriken
                        advanced_metrics["buy_pressure_ratio"],
                        advanced_metrics["unique_signer_ratio"]
                    ))
                    phases_in_batch.append(entry["meta"]["phase_id"])
                entry["buffer"] = self.get_empty_buffer()
                entry["next_flush"] = now_ts + entry["interval"]
        
        if batch_data and tracker_status["db_connected"]:
            sql = """
                INSERT INTO coin_metrics (
                    mint, timestamp, phase_id_at_time,
                    price_open, price_high, price_low, price_close, market_cap_close,
                    bonding_curve_pct, virtual_sol_reserves, is_koth,
                    volume_sol, buy_volume_sol, sell_volume_sol,
                    num_buys, num_sells, unique_wallets, num_micro_trades,
                    dev_sold_amount, max_single_buy_sol, max_single_sell_sol,
                    -- NEU: Erweiterte Metriken
                    net_volume_sol, volatility_pct, avg_trade_size_sol,
                    whale_buy_volume_sol, whale_sell_volume_sol,
                    num_whale_buys, num_whale_sells,
                    -- NEU: Ratio-Metriken
                    buy_pressure_ratio, unique_signer_ratio
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28, $29, $30)
            """
            try:
                with flush_duration.time():
                    async with self.pool.acquire() as conn:
                        await conn.executemany(sql, batch_data)
                counts = Counter(phases_in_batch)
                details = ", ".join([f"Phase {k}: {v}" for k,v in sorted(counts.items())])
                
                # Detailliertes Logging
                print(f"💾 Saved metrics for {len(batch_data)} coins ({details})", flush=True)
                
                    # Zeige Details für die ersten 3 Coins als Beispiel (inkl. erweiterte Metriken)
                for i, (mint, timestamp, phase_id, *rest) in enumerate(batch_data[:3]):
                    mint_short = mint[:8] + "..." if len(mint) > 8 else mint
                    # rest enthält: price_open, price_high, ..., max_single_sell_sol, net_volume_sol, volatility_pct, ...
                    if len(rest) >= 29:  # Mindestens 29 Werte (inkl. alle neuen Metriken)
                        dev_sold = rest[18] if len(rest) > 18 else 0  # dev_sold_amount (KRITISCH!)
                        net_vol = rest[20] if len(rest) > 20 else 0  # net_volume_sol
                        volatility = rest[21] if len(rest) > 21 else 0  # volatility_pct
                        avg_trade = rest[22] if len(rest) > 22 else 0  # avg_trade_size_sol
                        whale_buys = rest[25] if len(rest) > 25 else 0  # num_whale_buys
                        whale_sells = rest[26] if len(rest) > 26 else 0  # num_whale_sells
                        buy_pressure = rest[27] if len(rest) > 27 else 0  # buy_pressure_ratio
                        unique_ratio = rest[28] if len(rest) > 28 else 0  # unique_signer_ratio
                        dev_warning = "⚠️ DEV SOLD!" if dev_sold > 0 else ""
                        print(f"   ✓ {mint_short} - Phase {phase_id} - {timestamp.strftime('%H:%M:%S')} | Net: {net_vol:.2f} SOL | Vol: {volatility:.1f}% | Whales: {whale_buys}B/{whale_sells}S | BuyP: {buy_pressure:.2f} | Unique: {unique_ratio:.2f} {dev_warning}", flush=True)
                    else:
                        print(f"   ✓ {mint_short} - Phase {phase_id} - {timestamp.strftime('%H:%M:%S')}", flush=True)
                
                if len(batch_data) > 3:
                    print(f"   ... und {len(batch_data) - 3} weitere Coins", flush=True)
                
                metrics_saved.inc(len(batch_data))
                tracker_status["total_metrics_saved"] += len(batch_data)
                print(f"📊 Gesamt gespeichert: {tracker_status['total_metrics_saved']} Metriken", flush=True)
            except Exception as e:
                print(f"⚠️ SQL Error: {e}. Daten gehen verloren!", flush=True)
                tracker_status["db_connected"] = False
                db_connected.set(0)
                db_errors.labels(type="insert").inc()
        elif batch_data and not tracker_status["db_connected"]:
            print(f"⚠️ {len(batch_data)} Datenpunkte verloren (DB nicht verbunden)", flush=True)
            print(f"   Betroffene Coins: {[mint[:8] + '...' if len(mint) > 8 else mint for mint, *_ in batch_data[:5]]}", flush=True)

async def start_tracker():
    global _tracker_instance
    tracker = Tracker()
    # Speichere Tracker-Instanz für Health-Check
    _tracker_instance = tracker
    await tracker.run()

async def main():
    # Starte Health-Server ZUERST, damit er sofort verfügbar ist
    health_task = asyncio.create_task(start_health_server())
    # Warte kurz, damit Health-Server startet
    await asyncio.sleep(1)
    
    print(f"🔧 Konfiguration:", flush=True)
    print(f"  - DB_REFRESH_INTERVAL: {DB_REFRESH_INTERVAL}s", flush=True)
    print(f"  - WS_PING_INTERVAL: {WS_PING_INTERVAL}s", flush=True)
    print(f"  - WS_CONNECTION_TIMEOUT: {WS_CONNECTION_TIMEOUT}s", flush=True)
    print(f"  - WS_URI: {WS_URI}", flush=True)
    print(f"  - TRADE_BUFFER_SECONDS: {TRADE_BUFFER_SECONDS}s ({TRADE_BUFFER_SECONDS//60} Minuten) (Pre-Subscription + Buffer)", flush=True)
    # Health-Server läuft bereits (wurde oben gestartet)
    # Starte nur noch den Tracker
    await start_tracker()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Shutdown...", flush=True)

