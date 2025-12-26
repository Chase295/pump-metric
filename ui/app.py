import streamlit as st
import requests
import json
import yaml
import os
from datetime import datetime
import time
from pathlib import Path
import re
from urllib.parse import urlparse
import pandas as pd

# Konfiguration
CONFIG_FILE = "/app/config/config.yaml"
ENV_FILE = "/app/.env"  # .env Datei für Docker Compose
TRACKER_SERVICE = os.getenv("TRACKER_SERVICE", "tracker")  # Container-Name
TRACKER_PORT = int(os.getenv("TRACKER_PORT", "8000"))

st.set_page_config(
    page_title="Pump Metric - Control Panel",
    page_icon="📊",
    layout="wide"
)

def load_config():
    """Lädt Konfiguration aus Environment Variables (Coolify) oder Fallback auf Dateien"""
    config = {}
    
    # PRIORITÄT 1: Lade aus Environment Variables (Coolify verwendet diese)
    env_vars = {
        'DB_DSN': os.getenv('DB_DSN'),
        'WS_URI': os.getenv('WS_URI', 'wss://pumpportal.fun/api/data'),
        'DB_REFRESH_INTERVAL': os.getenv('DB_REFRESH_INTERVAL', '10'),
        'DB_RETRY_DELAY': os.getenv('DB_RETRY_DELAY', '5'),
        'WS_RETRY_DELAY': os.getenv('WS_RETRY_DELAY', '3'),
        'WS_MAX_RETRY_DELAY': os.getenv('WS_MAX_RETRY_DELAY', '60'),
        'WS_PING_INTERVAL': os.getenv('WS_PING_INTERVAL', '20'),
        'WS_PING_TIMEOUT': os.getenv('WS_PING_TIMEOUT', '10'),
        'WS_CONNECTION_TIMEOUT': os.getenv('WS_CONNECTION_TIMEOUT', '30'),
        'SOL_RESERVES_FULL': os.getenv('SOL_RESERVES_FULL', '85.0'),
        'AGE_CALCULATION_OFFSET_MIN': os.getenv('AGE_CALCULATION_OFFSET_MIN', '60'),
        'TRADE_BUFFER_SECONDS': os.getenv('TRADE_BUFFER_SECONDS', '180'),
        'HEALTH_PORT': os.getenv('HEALTH_PORT', '8000'),
    }
    
    # Konvertiere Environment Variables zu Config-Dict
    for key, value in env_vars.items():
        if value is not None:
            # Konvertiere Zahlen
            if value.isdigit():
                config[key] = int(value)
            else:
                try:
                    config[key] = float(value)
                except:
                    config[key] = value
    
    # Wenn Environment Variables vorhanden sind, verwende diese
    if config.get('DB_DSN'):
        return config
    
    # FALLBACK: Versuche YAML-Datei
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                file_config = yaml.safe_load(f)
                if file_config:
                    # Merge mit Environment Variables (Env hat Priorität)
                    file_config.update(config)
                    return file_config
        except Exception:
            pass
    
    # FALLBACK: Versuche .env Datei
    env_paths = ["/app/.env", "/app/../.env", "/app/config/.env", ".env"]
    for env_path in env_paths:
        if os.path.exists(env_path):
            try:
                with open(env_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip()
                            if key not in config:  # Nur wenn nicht bereits aus Env-Vars
                                if value.isdigit():
                                    config[key] = int(value)
                                else:
                                    try:
                                        config[key] = float(value)
                                    except:
                                        config[key] = value
            except Exception:
                continue
    
    # Wenn nichts gefunden wurde, verwende Defaults
    if not config:
        return get_default_config()
    
    return config

def save_config(config):
    """Speichert Konfiguration in YAML-Datei UND .env Datei"""
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    except (OSError, PermissionError):
        # Verzeichnis kann nicht erstellt werden (read-only)
        raise
    
    # Speichere YAML (für UI)
    try:
        with open(CONFIG_FILE, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
    except (OSError, PermissionError) as e:
        # Dateisystem ist read-only - wirf Exception weiter
        raise OSError(f"Config-Datei kann nicht geschrieben werden (read-only): {e}")
    
    # Speichere .env (für Tracker Service - im geteilten Volume)
    env_file = "/app/config/.env"  # Im geteilten Volume
    env_content = f"""# ============================================================================
# PUMP METRIC - Umgebungsvariablen
# ============================================================================
# Diese Datei wird automatisch von der Streamlit UI verwaltet.
# Änderungen können über den "Konfiguration neu laden" Button übernommen werden (ohne Neustart).
# ============================================================================

# Datenbank Einstellungen
DB_DSN={config.get('DB_DSN', 'postgresql://postgres:9HVxi6hN6j7xpmqUx84o@100.118.155.75:5432/crypto')}

# WebSocket Einstellungen
WS_URI={config.get('WS_URI', 'wss://pumpportal.fun/api/data')}
WS_RETRY_DELAY={config.get('WS_RETRY_DELAY', 3)}
WS_MAX_RETRY_DELAY={config.get('WS_MAX_RETRY_DELAY', 60)}
WS_PING_INTERVAL={config.get('WS_PING_INTERVAL', 20)}
WS_PING_TIMEOUT={config.get('WS_PING_TIMEOUT', 10)}
WS_CONNECTION_TIMEOUT={config.get('WS_CONNECTION_TIMEOUT', 30)}

# Datenbank Refresh Einstellungen
DB_REFRESH_INTERVAL={config.get('DB_REFRESH_INTERVAL', 10)}
DB_RETRY_DELAY={config.get('DB_RETRY_DELAY', 5)}

# Tracker Einstellungen
SOL_RESERVES_FULL={config.get('SOL_RESERVES_FULL', 85.0)}
AGE_CALCULATION_OFFSET_MIN={config.get('AGE_CALCULATION_OFFSET_MIN', 60)}
TRADE_BUFFER_SECONDS={config.get('TRADE_BUFFER_SECONDS', 180)}
WHALE_THRESHOLD_SOL={config.get('WHALE_THRESHOLD_SOL', 1.0)}

# Health-Check Port
HEALTH_PORT={config.get('HEALTH_PORT', 8000)}
"""
    try:
        os.makedirs(os.path.dirname(env_file), exist_ok=True)
        with open(env_file, 'w') as f:
            f.write(env_content)
    except (OSError, PermissionError) as e:
        # .env Datei kann nicht geschrieben werden - ignorieren (optional)
        pass  # Optional - nicht kritisch
    
    return True  # YAML wurde immer gespeichert

def get_default_config():
    """Gibt Standard-Konfiguration zurück"""
    return {
        "DB_DSN": "postgresql://postgres:9HVxi6hN6j7xpmqUx84o@100.118.155.75:5432/crypto",
        "WS_URI": "wss://pumpportal.fun/api/data",
        "DB_REFRESH_INTERVAL": 10,
        "SOL_RESERVES_FULL": 85.0,
        "AGE_CALCULATION_OFFSET_MIN": 60,
        "DB_RETRY_DELAY": 5,
        "WS_RETRY_DELAY": 3,
        "WS_MAX_RETRY_DELAY": 60,
        "WS_PING_INTERVAL": 20,
        "WS_PING_TIMEOUT": 10,
        "WS_CONNECTION_TIMEOUT": 30,
        "HEALTH_PORT": 8000
    }

def validate_url(url, allow_empty=False):
    """Validiert eine URL"""
    if allow_empty and not url:
        return True, None
    if not url:
        return False, "URL darf nicht leer sein"
    try:
        result = urlparse(url)
        if not result.scheme or not result.netloc:
            return False, "Ungültige URL-Format"
        if result.scheme not in ["http", "https", "wss", "ws", "postgresql"]:
            return False, f"Ungültiges Protokoll: {result.scheme}. Erlaubt: http, https, ws, wss, postgresql"
        return True, None
    except Exception as e:
        return False, f"URL-Validierungsfehler: {str(e)}"

def validate_port(port):
    """Validiert einen Port"""
    try:
        port_int = int(port)
        if 1 <= port_int <= 65535:
            return True, None
        return False, "Port muss zwischen 1 und 65535 liegen"
    except ValueError:
        return False, "Port muss eine Zahl sein"

def get_tracker_health():
    """Holt Health-Status vom Tracker-Service"""
    try:
        # Versuche zuerst über Docker-Netzwerk (Service-Name)
        response = requests.get(f"http://{TRACKER_SERVICE}:{TRACKER_PORT}/health", timeout=2)
        if response.status_code == 200:
            return response.json()
    except:
        try:
            # Fallback: Versuche über localhost (wenn UI außerhalb Docker läuft)
            response = requests.get(f"http://localhost:8011/health", timeout=2)
            if response.status_code == 200:
                return response.json()
        except:
            pass
    return None

def reload_tracker_config():
    """Lädt die Konfiguration im Tracker-Service neu (ohne Neustart)"""
    try:
        # POST-Request an Tracker-Service
        response = requests.post(
            f"http://{TRACKER_SERVICE}:{TRACKER_PORT}/reload-config",
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            return True, data.get("message", "Konfiguration wurde neu geladen")
        else:
            return False, f"Fehler: HTTP {response.status_code}"
    except requests.exceptions.ConnectionError:
        return False, "Verbindung zum Tracker-Service fehlgeschlagen. Ist der Service gestartet?"
    except Exception as e:
        return False, f"Fehler beim Neuladen: {str(e)}"

def get_tracker_metrics():
    """Holt Prometheus Metrics vom Tracker-Service"""
    try:
        # Versuche zuerst über Docker-Netzwerk (Service-Name)
        response = requests.get(f"http://{TRACKER_SERVICE}:{TRACKER_PORT}/metrics", timeout=2)
        if response.status_code == 200:
            return response.text
    except:
        try:
            # Fallback: Versuche über localhost (wenn UI außerhalb Docker läuft)
            response = requests.get(f"http://localhost:8011/metrics", timeout=2)
            if response.status_code == 200:
                return response.text
        except:
            pass
    return None

def restart_service():
    """Startet Tracker-Service neu (über Docker API, damit .env neu geladen wird)"""
    try:
        import docker
        client = docker.from_env()
        
        # Versuche verschiedene Container-Namen
        container_names = ["pump-metric-tracker", "tracker", TRACKER_SERVICE]
        container = None
        for name in container_names:
            try:
                container = client.containers.get(name)
                break
            except docker.errors.NotFound:
                continue
        
        # Falls nicht gefunden: Suche nach Containern mit "tracker" im Namen
        if not container:
            try:
                all_containers = client.containers.list(all=True)
                for cont in all_containers:
                    if "tracker" in cont.name.lower():
                        container = cont
                        break
            except Exception:
                pass
        
        if not container:
            return False, "Tracker-Container nicht gefunden. Bitte prüfe ob der Service läuft."
        
        # Stoppe Container
        container.stop(timeout=10)
        
        # Starte Container neu (lädt .env neu)
        container.start()
        
        return True, "Service erfolgreich neu gestartet! Neue Environment Variables werden geladen."
        
    except ImportError:
        # Docker Python Client nicht verfügbar - versuche über Docker Socket direkt
        try:
            import subprocess
            import os
            
            # Prüfe ob docker compose verfügbar ist
            docker_compose_cmd = None
            for cmd in ["docker", "docker-compose"]:
                try:
                    result = subprocess.run(
                        [cmd, "--version"],
                        capture_output=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        docker_compose_cmd = cmd
                        break
                except:
                    continue
            
            if not docker_compose_cmd:
                return False, "Docker/Docker Compose nicht gefunden. Bitte manuell neu starten: docker compose restart tracker"
            
            # Versuche über Docker Socket zu arbeiten
            compose_file = "/app/../docker-compose.yml"
            if not os.path.exists(compose_file):
                compose_file = "/app/docker-compose.yml"
            
            if os.path.exists(compose_file):
                work_dir = os.path.dirname(compose_file)
                result = subprocess.run(
                    [docker_compose_cmd, "restart", "tracker"],
                    cwd=work_dir,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode == 0:
                    return True, "Service neu gestartet (via docker compose)"
                else:
                    return False, f"Docker Compose Fehler: {result.stderr}"
            else:
                return False, "docker-compose.yml nicht gefunden"
                
        except Exception as e:
            return False, f"Fehler: {str(e)}"
    except Exception as e:
        return False, f"Fehler: {str(e)}"

def get_service_logs(lines=100):
    """Holt Logs vom Tracker-Service"""
    try:
        import docker
        client = docker.from_env()
        
        # Versuche verschiedene Container-Namen
        container_names = ["pump-metric-tracker", "tracker", TRACKER_SERVICE]
        container = None
        
        # Zuerst: Versuche direkte Container-Namen
        for name in container_names:
            try:
                container = client.containers.get(name)
                break
            except docker.errors.NotFound:
                continue
            except Exception as e:
                print(f"Fehler beim Zugriff auf Container {name}: {e}", flush=True)
                continue
        
        # Falls nicht gefunden: Suche nach Containern mit "tracker" im Namen
        if not container:
            try:
                all_containers = client.containers.list(all=True)
                for cont in all_containers:
                    # Suche nach Containern die "tracker" im Namen haben
                    if "tracker" in cont.name.lower() or "tracker" in (cont.name or "").lower():
                        container = cont
                        break
            except Exception as e:
                print(f"Fehler beim Durchsuchen der Container: {e}", flush=True)
        
        if container:
            try:
                logs = container.logs(tail=lines, timestamps=True).decode('utf-8')
                # Logs umkehren, damit neueste oben stehen
                log_lines = logs.strip().split('\n')
                reversed_logs = '\n'.join(reversed(log_lines))
                return reversed_logs
            except Exception as e:
                return f"Fehler beim Lesen der Logs: {str(e)}"
        else:
            # Liste alle verfügbaren Container für Debugging
            try:
                all_containers = client.containers.list(all=True)
                container_list = [c.name for c in all_containers[:10]]  # Erste 10
                return f"❌ Tracker-Container nicht gefunden.\n\nVerfügbare Container (erste 10): {', '.join(container_list)}\n\nBitte prüfe ob der Tracker-Service läuft."
            except:
                return "❌ Tracker-Container nicht gefunden. Bitte prüfe ob der Service läuft."
    except ImportError:
        # Fallback: Docker Python Client nicht verfügbar - versuche über docker compose
        import subprocess
        import os
        try:
            # Versuche verschiedene Wege zum docker-compose.yml
            compose_paths = ["/app/../docker-compose.yml", "/app/docker-compose.yml", "./docker-compose.yml"]
            work_dir = "/app"
            
            for path in compose_paths:
                if os.path.exists(path):
                    work_dir = os.path.dirname(path)
                    break
            
            result = subprocess.run(
                ["docker", "compose", "logs", "--tail", str(lines), "tracker"],
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                # Logs umkehren, damit neueste oben stehen
                log_lines = result.stdout.strip().split('\n')
                reversed_logs = '\n'.join(reversed(log_lines))
                return reversed_logs
            else:
                return f"Fehler beim Abrufen der Logs: {result.stderr}"
        except Exception as e:
            return f"Fehler beim Abrufen der Logs: {str(e)}"
    except Exception as e:
        return f"Fehler beim Abrufen der Logs: {str(e)}"

# Header
st.title("📊 Pump Metric - Control Panel")

# Tabs Navigation
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Dashboard", "⚙️ Konfiguration", "📋 Logs", "📈 Metriken", "📖 Info"])

# Dashboard Tab
with tab1:
    st.title("📊 Dashboard")
    
    # Health Status
    health = get_tracker_health()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if health:
            status = "🟢 Online" if (health.get("db_connected") and health.get("ws_connected")) else "🔴 Offline"
            st.metric("Status", status)
        else:
            st.metric("Status", "❌ Nicht erreichbar")
    
    with col2:
        if health:
            st.metric("Trades verarbeitet", health.get("total_trades", 0))
        else:
            st.metric("Trades verarbeitet", "-")
    
    with col3:
        if health:
            st.metric("Metriken gespeichert", health.get("total_metrics_saved", 0))
        else:
            st.metric("Metriken gespeichert", "-")
    
    with col4:
        if health:
            uptime = health.get("uptime_seconds", 0)
            hours = uptime // 3600
            minutes = (uptime % 3600) // 60
            st.metric("Uptime", f"{int(hours)}h {int(minutes)}m")
        else:
            st.metric("Uptime", "-")
    
    # Detaillierte Informationen
    if health:
        st.subheader("📈 Detaillierte Informationen")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**WebSocket Status:**")
            st.write(f"- Verbunden: {'✅' if health.get('ws_connected') else '❌'}")
            st.write(f"- Reconnects: {health.get('reconnect_count', 0)}")
            if health.get('last_message_ago'):
                st.write(f"- Letzte Nachricht: vor {health.get('last_message_ago')}s")
            
            st.write("**Datenbank Status:**")
            st.write(f"- Verbunden: {'✅' if health.get('db_connected') else '❌'}")
            if health.get('last_error'):
                st.write(f"- Letzter Fehler: {health.get('last_error')}")
        
        with col2:
            st.write("**Tracker-Statistiken:**")
            st.write(f"- Gesamt Trades: {health.get('total_trades', 0)}")
            st.write(f"- Gesamt Metriken: {health.get('total_metrics_saved', 0)}")
            
            # NEU: Erweiterte Metriken-Info
            st.write("**Erweiterte Metriken:**")
            st.write("✅ Whale-Tracking aktiv")
            st.write("✅ Volatilität wird berechnet")
            st.write("✅ Netto-Volumen wird berechnet")
            st.write("✅ Durchschnittliche Trade-Größe wird berechnet")
            
            # Buffer-Statistiken aus Health-Endpoint
            buffer_stats = health.get('buffer_stats', {})
            if buffer_stats:
                st.write("**Buffer-System:**")
                st.write(f"- Trades im Buffer: {buffer_stats.get('total_trades_in_buffer', 0)}")
                st.write(f"- Coins mit Buffer: {buffer_stats.get('coins_with_buffer', 0)}")
                
                # Detaillierte Buffer-Info
                buffer_details = buffer_stats.get('buffer_details', {})
                if buffer_details:
                    st.write("**Top Coins im Buffer:**")
                    for coin, count in list(buffer_details.items())[:5]:
                        st.write(f"  • {coin}: {count} Trades")
            
            # Fallback: Metriken falls Health-Endpoint keine Buffer-Info hat
            elif not buffer_stats:
                metrics = get_tracker_metrics()
                if metrics:
                    metrics_dict = {}
                    for line in metrics.split('\n'):
                        if line and not line.startswith('#'):
                            parts = line.split()
                            if len(parts) >= 2:
                                metrics_dict[parts[0]] = parts[1]
                    
                    buffer_size = metrics_dict.get('tracker_trade_buffer_size', '0')
                    buffer_trades = metrics_dict.get('tracker_buffer_trades_total', '0')
                    trades_from_buffer = metrics_dict.get('tracker_trades_from_buffer_total', '0')
                    
                    st.write("**Buffer-System:**")
                    st.write(f"- Trades im Buffer: {buffer_size}")
                    st.write(f"- Gesamt im Buffer gespeichert: {buffer_trades}")
                    st.write(f"- Aus Buffer verarbeitet: {trades_from_buffer}")
    
    # Neustart-Button
    st.subheader("🔧 Service-Management")
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔄 Service neu starten", type="primary"):
            with st.spinner("Service wird neu gestartet..."):
                success, message = restart_service()
                if success:
                    st.success(message)
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error(message)
    
    with col2:
        if st.button("🔄 Seite aktualisieren"):
            st.rerun()
    
    # Auto-Refresh
    if st.checkbox("🔄 Auto-Refresh (5s)"):
        time.sleep(5)
        st.rerun()

# Konfiguration Tab
with tab2:
    try:
        config = load_config()
    except Exception as e:
        # Falls load_config fehlschlägt (z.B. read-only FS), verwende Default-Config
        print(f"⚠️ Fehler beim Laden der Config: {e}. Verwende Default-Config.", flush=True)
        config = get_default_config()
    
    # Prüfe ob Environment Variables verwendet werden (Coolify)
    using_env_vars = bool(os.getenv('DB_DSN'))
    
    if using_env_vars:
        st.warning("⚠️ **Coolify-Modus:** Die Konfiguration wird über Environment Variables verwaltet. Änderungen müssen in der Coolify Web-UI gemacht werden, nicht hier!")
        st.info("💡 Gehe zu deiner Coolify-Anwendung → Environment Variables, um die Einstellungen zu ändern. Nach Änderungen muss die Anwendung neu deployed werden.")
    else:
        st.info("💡 Änderungen werden in der Konfigurationsdatei gespeichert. Ein Service-Neustart ist erforderlich, damit die Änderungen wirksam werden.")
    
    with st.form("config_form"):
        st.subheader("🗄️ Datenbank Einstellungen")
        config["DB_DSN"] = st.text_input("DB DSN", value=config.get("DB_DSN", ""), help="PostgreSQL Connection String")
        if config["DB_DSN"]:
            db_valid, db_error = validate_url(config["DB_DSN"], allow_empty=False)
            if not db_valid:
                st.error(f"❌ {db_error}")
        config["DB_REFRESH_INTERVAL"] = st.number_input("DB Refresh Interval (Sekunden)", min_value=1, max_value=300, value=config.get("DB_REFRESH_INTERVAL", 10))
        config["DB_RETRY_DELAY"] = st.number_input("DB Retry Delay (Sekunden)", min_value=1, max_value=60, value=config.get("DB_RETRY_DELAY", 5))
        
        st.subheader("🌐 WebSocket Einstellungen")
        config["WS_URI"] = st.text_input("WebSocket URI", value=config.get("WS_URI", ""))
        if config["WS_URI"]:
            ws_valid, ws_error = validate_url(config["WS_URI"], allow_empty=False)
            if not ws_valid:
                st.error(f"❌ {ws_error}")
        config["WS_RETRY_DELAY"] = st.number_input("WS Retry Delay (Sekunden)", min_value=1, max_value=300, value=config.get("WS_RETRY_DELAY", 3))
        config["WS_MAX_RETRY_DELAY"] = st.number_input("WS Max Retry Delay (Sekunden)", min_value=1, max_value=600, value=config.get("WS_MAX_RETRY_DELAY", 60))
        config["WS_PING_INTERVAL"] = st.number_input("WS Ping Interval (Sekunden)", min_value=1, max_value=300, value=config.get("WS_PING_INTERVAL", 20))
        config["WS_PING_TIMEOUT"] = st.number_input("WS Ping Timeout (Sekunden)", min_value=1, max_value=300, value=config.get("WS_PING_TIMEOUT", 10))
        config["WS_CONNECTION_TIMEOUT"] = st.number_input("WS Connection Timeout (Sekunden)", min_value=1, max_value=600, value=config.get("WS_CONNECTION_TIMEOUT", 30))
        
        st.subheader("📊 Tracker Einstellungen")
        config["SOL_RESERVES_FULL"] = st.number_input("SOL Reserves Full", min_value=1.0, max_value=1000.0, value=float(config.get("SOL_RESERVES_FULL", 85.0)), step=0.1)
        config["AGE_CALCULATION_OFFSET_MIN"] = st.number_input("Age Calculation Offset (Minuten)", min_value=0, max_value=1440, value=config.get("AGE_CALCULATION_OFFSET_MIN", 60))
        
        st.subheader("🔧 Sonstige Einstellungen")
        config["HEALTH_PORT"] = st.number_input("Health Port", min_value=1000, max_value=65535, value=config.get("HEALTH_PORT", 8000))
        port_valid, port_error = validate_port(config["HEALTH_PORT"])
        if not port_valid:
            st.error(f"❌ {port_error}")
        
        col1, col2 = st.columns(2)
        with col1:
            save_button = st.form_submit_button("💾 Konfiguration speichern", type="primary", disabled=using_env_vars)
        with col2:
            reset_button = st.form_submit_button("🔄 Auf Standard zurücksetzen", disabled=using_env_vars)
        
        if using_env_vars:
            st.warning("⚠️ **Speichern deaktiviert:** In Coolify müssen Änderungen über Environment Variables in der Coolify Web-UI gemacht werden!")
            st.info("💡 **Alternative:** Du kannst die Konfiguration trotzdem speichern und dann über den 'Konfiguration neu laden' Button übernehmen (funktioniert auch in Coolify).")
        
        if save_button:
            # Validierung vor dem Speichern
            errors = []
            
            # URL-Validierung
            db_valid, db_error = validate_url(config["DB_DSN"], allow_empty=False)
            if not db_valid:
                errors.append(f"DB DSN: {db_error}")
            
            ws_valid, ws_error = validate_url(config["WS_URI"], allow_empty=False)
            if not ws_valid:
                errors.append(f"WebSocket URI: {ws_error}")
            
            # Port-Validierung
            port_valid, port_error = validate_port(config["HEALTH_PORT"])
            if not port_valid:
                errors.append(f"Health Port: {port_error}")
            
            if errors:
                st.error("❌ **Validierungsfehler:**")
                for error in errors:
                    st.error(f"  - {error}")
            else:
                if using_env_vars:
                    st.error("❌ **Fehler:** In Coolify können Konfigurationen nicht über die UI gespeichert werden. Bitte verwende die Coolify Web-UI → Environment Variables.")
                else:
                    try:
                        result = save_config(config)
                        if result:
                            st.session_state.config_saved = True
                            st.success("✅ Konfiguration gespeichert!")
                            
                            st.info("💡 **Tipp:** Du kannst die Konfiguration jetzt ohne Neustart übernehmen! Nutze den 'Konfiguration neu laden' Button unten.")
                    except (OSError, PermissionError) as e:
                        st.error(f"❌ **Fehler beim Speichern:** {e}")
                        st.info("💡 Das Dateisystem ist möglicherweise read-only. In Coolify verwende bitte Environment Variables in der Web-UI.")
        
        if reset_button:
            default_config = get_default_config()
            if save_config(default_config):
                st.session_state.config_saved = True
                st.success("✅ Konfiguration auf Standard zurückgesetzt!")
                st.warning("⚠️ Bitte Service neu starten, damit die Änderungen wirksam werden.")
                st.rerun()
    
    # Neustart-Button außerhalb des Forms (wenn Konfiguration gespeichert wurde)
    if st.session_state.get("config_saved", False):
        st.divider()
        st.subheader("🔄 Service-Neustart")
        col1, col2 = st.columns([2, 1])
        with col1:
            st.info("💡 Die Konfiguration wurde gespeichert. Starte den Tracker-Service neu, damit die neuen Werte geladen werden.")
        with col2:
            if st.button("🔄 Tracker-Service neu starten", type="primary", use_container_width=True):
                with st.spinner("Tracker-Service wird neu gestartet..."):
                    success, message = restart_service()
                    if success:
                        st.success(message)
                        st.info("⏳ Bitte warte 5-10 Sekunden, bis der Service vollständig neu gestartet ist.")
                        st.session_state.config_saved = False  # Reset Flag
                        time.sleep(3)
                        st.rerun()
                    else:
                        st.error(message)
                        st.info("💡 Du kannst den Service auch manuell neu starten: `docker compose restart tracker`")
    
    # Aktuelle Konfiguration anzeigen
    st.subheader("📄 Aktuelle Konfiguration")
    st.json(config)

# Logs Tab
with tab3:
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        lines = st.number_input("Anzahl Zeilen", min_value=10, max_value=1000, value=100, step=10, key="logs_lines_input")
    
    with col2:
        refresh_logs = st.button("🔄 Logs aktualisieren", type="primary")
    
    # Logs laden (immer neu, damit sie aktuell sind)
    logs = get_service_logs(lines=lines)
    
    # Info-Banner oben
    st.info("📋 **Neueste Logs stehen oben** - Die Logs werden automatisch umgekehrt angezeigt, damit die neuesten Einträge zuerst erscheinen.")
    
    # Text-Area für Logs (ohne key, damit es immer aktualisiert wird)
    st.text_area("Service Logs (neueste oben)", logs, height=600, key=f"logs_display_{time.time() if refresh_logs else 'default'}")
    
    # Info wenn Logs leer sind
    if not logs or logs.strip() == "":
        st.warning("⚠️ Keine Logs verfügbar. Prüfe ob der Tracker-Service läuft.")
    
    # Auto-Refresh Checkbox
    auto_refresh = st.checkbox("🔄 Auto-Refresh Logs (10s)", key="auto_refresh_logs")
    if auto_refresh:
        time.sleep(10)
        st.rerun()

# Metriken Tab
with tab4:
    
    if st.button("🔄 Metriken aktualisieren"):
        st.rerun()
    
    # Buffer-Details Sektion
    st.subheader("💾 Buffer-System Details")
    health = get_tracker_health()
    if health and health.get('buffer_stats'):
        buffer_stats = health['buffer_stats']
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Trades im Buffer", buffer_stats.get('total_trades_in_buffer', 0))
        with col2:
            st.metric("Coins mit Buffer", buffer_stats.get('coins_with_buffer', 0))
        with col3:
            metrics = get_tracker_metrics()
            if metrics:
                metrics_dict = {}
                for line in metrics.split('\n'):
                    if line and not line.startswith('#'):
                        parts = line.split()
                        if len(parts) >= 2:
                            metrics_dict[parts[0]] = parts[1]
                trades_from_buffer = metrics_dict.get('tracker_trades_from_buffer_total', '0')
                st.metric("Aus Buffer verarbeitet", trades_from_buffer)
        
        # Detaillierte Liste der Coins im Buffer
        buffer_details = buffer_stats.get('buffer_details', {})
        if buffer_details:
            st.write("**Coins mit Trades im Buffer:**")
            # Verwende Streamlit's eingebautes DataFrame (pandas ist in Streamlit verfügbar)
            try:
                import pandas as pd
                buffer_df = pd.DataFrame([
                    {"Coin": coin, "Trades im Buffer": count}
                    for coin, count in buffer_details.items()
                ])
                st.dataframe(buffer_df, use_container_width=True, hide_index=True)
            except ImportError:
                # Fallback: Zeige als Tabelle ohne pandas
                st.table([
                    {"Coin": coin, "Trades im Buffer": count}
                    for coin, count in buffer_details.items()
                ])
        else:
            st.info("Keine Coins mit Trades im Buffer")
    
    st.divider()
    
    metrics = get_tracker_metrics()
    
    if metrics:
        # Parse und zeige wichtige Metriken
        st.subheader("📈 Wichtige Metriken")
        
        metrics_dict = {}
        for line in metrics.split('\n'):
            if line and not line.startswith('#'):
                parts = line.split()
                if len(parts) >= 2:
                    metric_name = parts[0]
                    metric_value = parts[1]
                    metrics_dict[metric_name] = metric_value
        
        # Wichtige Metriken anzeigen
        important_metrics = [
            'tracker_trades_received_total',
            'tracker_trades_processed_total',
            'tracker_trades_from_buffer_total',
            'tracker_metrics_saved_total',
            'tracker_coins_tracked',
            'tracker_coins_graduated_total',
            'tracker_coins_finished_total',
            'tracker_phase_switches_total',
            'tracker_ws_reconnects_total',
            'tracker_ws_connected',
            'tracker_db_connected',
            'tracker_uptime_seconds',
            'tracker_trade_buffer_size',
            'tracker_buffer_trades_total'
        ]
        
        cols = st.columns(3)
        col_idx = 0
        for metric in important_metrics:
            if metric in metrics_dict:
                with cols[col_idx % 3]:
                    st.metric(metric.replace('tracker_', '').replace('_', ' ').title(), metrics_dict[metric])
                col_idx += 1
        
        # NEU: Erweiterte Metriken-Info
        st.divider()
        st.subheader("📊 Erweiterte Metriken (aus coin_metrics)")
        
        st.info("""
        **Hinweis**: Die erweiterten Metriken (Whale-Tracking, Volatilität, Netto-Volumen, etc.) 
        werden in der Datenbank gespeichert und können über SQL-Abfragen abgerufen werden.
        
        **Verfügbare Metriken**:
        - `net_volume_sol`: Netto-Volumen (Delta: Buy - Sell)
        - `volatility_pct`: Volatilität in Prozent
        - `avg_trade_size_sol`: Durchschnittliche Trade-Größe
        - `whale_buy_volume_sol`: Whale-Buy-Volumen
        - `whale_sell_volume_sol`: Whale-Sell-Volumen
        - `num_whale_buys`: Anzahl Whale-Buys
        - `num_whale_sells`: Anzahl Whale-Sells
        """)
        
        st.markdown("""
        **Beispiel-SQL-Abfrage**:
        ```sql
        SELECT 
            mint,
            timestamp,
            net_volume_sol,
            volatility_pct,
            avg_trade_size_sol,
            whale_buy_volume_sol,
            num_whale_buys
        FROM coin_metrics
        WHERE timestamp >= NOW() - INTERVAL '1 hour'
        ORDER BY timestamp DESC
        LIMIT 10;
        ```
        """)
        
        # Vollständige Metriken
        st.divider()
        st.subheader("📄 Vollständige Metriken (Raw)")
        st.code(metrics, language="text")
    else:
        st.error("❌ Metriken konnten nicht abgerufen werden. Bitte prüfe, ob der Tracker-Service läuft.")
    
    if st.checkbox("🔄 Auto-Refresh Metriken (5s)"):
        time.sleep(5)
        st.rerun()

# Info Tab
with tab5:
    st.title("📖 System-Informationen & Funktionsweise")
    
    st.markdown("""
    ## 🎯 Übersicht
    
    Das **Pump Metric** System ist Teil eines größeren Workflows. Zuerst werden Coins **entdeckt** (pump-discover), 
    dann werden sie **getrackt** (pump-metric). Diese Seite erklärt beide Prozesse.
    """)
    
    st.divider()
    
    st.header("🔍 Phase 0: Coin Discovery (pump-discover)")
    
    st.markdown("""
    **Bevor** ein Coin getrackt werden kann, muss er zuerst **entdeckt** werden. Dieser Prozess läuft im 
    separaten `pump-discover` System.
    """)
    
    st.subheader("📡 Schritt 1: WebSocket - Neue Coins empfangen")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        ### Datenquelle 1: WebSocket (create Event)
        - **Quelle**: `wss://pumpportal.fun/api/data`
        - **Event**: `create` (neue Token-Erstellung)
        - **Daten**: Basis-Informationen über den neuen Coin
        
        **Enthaltene Felder**:
        - `mint`: Token-Adresse
        - `name`, `symbol`: Name und Symbol
        - `signature`: Transaktions-Signatur
        - `traderPublicKey`: Creator-Adresse
        - `bondingCurveKey`: Bonding Curve Adresse
        - `vSolInBondingCurve`: Virtuelles SOL
        - `vTokensInBondingCurve`: Virtuelle Tokens
        - `marketCapSol`: Market Cap
        - `uri`: Metadata-URI
        """)
    
    with col2:
        st.markdown("""
        ### Datenfluss
        ```
        Pump.fun WebSocket
            ↓
        Python Relay (pump-discover)
            ↓
        n8n Workflow (Filterung)
            ↓
        Datenbank (discovered_coins)
        ```
        
        **Wichtig**: Der Relay filtert bereits Spam-Coins basierend auf:
        - Bad Names Pattern (test, bot, rug, scam, etc.)
        - Spam-Burst-Erkennung
        """)
    
    st.subheader("🔍 Schritt 2: API-Daten abrufen")
    
    st.markdown("""
    Für jeden entdeckten Coin werden **zusätzliche Daten** von einer Token-Analyse-API abgerufen:
    """)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        ### Datenquelle 2: API (Token-Analyse)
        
        **Abgerufene Felder**:
        - `token.decimals`: Token-Decimals (z.B. 6)
        - `token.supply`: Token-Supply (raw, mit Decimals)
        - `deployPlatform`: Deployment-Platform (z.B. "rapidlaunch")
        
        **Beispiel**:
        ```json
        {
          "token": {
            "decimals": 6,
            "supply": 1000000000000000
          },
          "deployPlatform": "rapidlaunch"
        }
        ```
        """)
    
    with col2:
        st.markdown("""
        ### Verwendung in n8n
        
        Diese Daten werden mit einem **HTTP Request Node** abgerufen:
        - Endpoint: Token-Analyse-API
        - Parameter: `{mint}` (Token-Adresse)
        - Mapping: `token_decimals`, `token_supply`, `deploy_platform`
        
        **Hinweis**: Die API-Daten müssen separat abgerufen werden, 
        sie kommen nicht direkt vom WebSocket.
        """)
    
    st.subheader("📄 Schritt 3: Metadata abrufen")
    
    st.markdown("""
    Aus der `uri` (vom WebSocket) werden **Metadata** abgerufen:
    """)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        ### Datenquelle 3: Metadata (aus URI)
        
        **Enthaltene Felder**:
        - `description`: Token-Beschreibung
        - `image`: Bild-URL
        - `twitter`: Twitter/X URL
        - `telegram`: Telegram URL
        - `website`: Website URL
        - `discord`: Discord URL (falls vorhanden)
        """)
    
    with col2:
        st.markdown("""
        ### Verarbeitung
        
        - URI wird in n8n geparst (IPFS/RapidLaunch)
        - Metadata wird abgerufen
        - Social Media Links werden extrahiert
        - `has_socials` Flag wird gesetzt
        """)
    
    st.subheader("💾 Schritt 4: In Datenbank speichern")
    
    st.markdown("""
    Alle gesammelten Daten werden in die Tabelle `discovered_coins` gespeichert:
    """)
    
    st.code("""
    INSERT INTO discovered_coins (
        -- Identifikation
        token_address, symbol, name,
        token_decimals, token_supply, deploy_platform,
        
        -- Transaktions-Info
        signature, trader_public_key,
        
        -- Bonding Curve
        bonding_curve_key, v_sol_in_bonding_curve, 
        v_tokens_in_bonding_curve,
        
        -- Initial Buy
        initial_buy_sol, initial_buy_tokens,
        
        -- Preis & Market Cap
        price_sol, market_cap_sol, liquidity_sol,
        
        -- Metadata
        metadata_uri, description, image_url,
        twitter_url, telegram_url, website_url,
        
        -- Risiko & Analyse
        risk_score, top_10_holders_pct, has_socials,
        
        -- Status
        is_active, is_graduated, phase_id
    ) VALUES (...);
    """, language="sql")
    
    st.info("""
    💡 **Wichtig**: Die Tabelle `discovered_coins` enthält **alle** entdeckten Coins mit vollständigen 
    Metadaten. Dies ist die Basis für das spätere Tracking.
    """)
    
    st.subheader("🔄 Schritt 5: Coin Stream erstellen")
    
    st.markdown("""
    Nachdem ein Coin in `discovered_coins` gespeichert wurde, wird ein **Stream-Eintrag** erstellt:
    """)
    
    st.code("""
    INSERT INTO coin_streams (
        token_address,        -- Verweis auf discovered_coins
        current_phase_id,     -- Start-Phase (meist 1)
        is_active,            -- TRUE = wird getrackt
        is_graduated,         -- FALSE (noch nicht graduiert)
        started_at            -- Zeitpunkt des Starts
    ) VALUES (...);
    """, language="sql")
    
    st.markdown("""
    **Zweck**: Die Tabelle `coin_streams` steuert, welche Coins vom **pump-metric** System getrackt werden.
    Nur Coins mit `is_active = TRUE` werden für das Tracking berücksichtigt.
    """)
    
    st.success("""
    ✅ **Zusammenfassung Discovery**: 
    1. WebSocket empfängt neue Coins
    2. n8n filtert und verarbeitet
    3. API-Daten werden abgerufen
    4. Metadata wird geparst
    5. Alles wird in `discovered_coins` gespeichert
    6. Ein Stream-Eintrag in `coin_streams` wird erstellt
    7. **Jetzt kann das Tracking beginnen!**
    """)
    
    st.divider()
    
    st.header("📊 Phase 1: Coin Tracking (pump-metric)")
    
    st.markdown("""
    **Nach** der Discovery beginnt das **Metric-Tracking**. Dieser Prozess läuft im `pump-metric` System.
    """)
    
    st.divider()
    
    st.header("🔍 Was macht das pump-metric Skript genau?")
    
    st.markdown("""
    Das **pump-metric** Skript ist ein kontinuierlich laufender Prozess, der folgendes tut:
    """)
    
    st.subheader("📋 Hauptaufgaben")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        **1. Datenbank-Synchronisation**
        - Liest alle aktiven Coins aus `coin_streams`
        - Aktualisiert die Watchlist alle 10 Sekunden
        - Fügt neue Coins hinzu, entfernt inaktive
        
        **2. WebSocket-Management**
        - Abonniert Trades für alle aktiven Coins
        - Empfängt Live-Trade-Events in Echtzeit
        - Verwaltet Reconnects automatisch
        """)
    
    with col2:
        st.markdown("""
        **3. Trade-Verarbeitung**
        - Verarbeitet jeden Trade sofort
        - Sammelt Daten in Buffern
        - Berechnet Metriken in Echtzeit
        
        **4. Metrik-Speicherung**
        - Speichert Metriken periodisch in DB
        - Verwaltet Phasen-Upgrades
        - Erkennt Graduierungen automatisch
        """)
    
    st.subheader("🔄 Detaillierter Ablauf")
    
    st.markdown("""
    ### Schritt 1: Datenbank-Abfrage (alle 10 Sekunden)
    
    **Was passiert:**
    ```sql
    SELECT cs.token_address, cs.current_phase_id, dc.token_created_at
    FROM coin_streams cs
    JOIN discovered_coins dc ON cs.token_address = dc.token_address
    WHERE cs.is_active = TRUE
    ```
    
    **Was wird aktualisiert:**
    - **Watchlist**: Liste aller zu trackenden Coins im Speicher
    - **Subscriptions**: Neue Coins werden zum WebSocket-Subscription hinzugefügt
    - **Buffer-Initialisierung**: Für jeden neuen Coin wird ein leerer Buffer erstellt
    
    **Auf Grundlage welcher Daten:**
    - `coin_streams.is_active = TRUE` → Welche Coins getrackt werden sollen
    - `coin_streams.current_phase_id` → Start-Phase für den Coin
    - `discovered_coins.token_created_at` → Wann der Coin erstellt wurde (für Altersberechnung)
    """)
    
    st.markdown("""
    ### Schritt 2: Trade-Empfang & Verarbeitung (kontinuierlich)
    
    **Was passiert bei jedem Trade:**
    
    **Eingehende Daten vom WebSocket:**
    ```json
    {
      "mint": "Token-Adresse",
      "txType": "buy" oder "sell",
      "solAmount": 0.5,                    // SOL-Betrag
      "vSolInBondingCurve": 10.5,         // Virtuelles SOL
      "vTokensInBondingCurve": 1000000,   // Virtuelle Tokens
      "traderPublicKey": "Wallet-Adresse"
    }
    ```
    
    **Was wird berechnet:**
    
    1. **Preis-Berechnung**:
       ```python
       price = vSolInBondingCurve / vTokensInBondingCurve
       ```
       - **Beispiel**: 10.5 SOL / 1.000.000 Tokens = 0.0000105 SOL pro Token
    
    2. **OHLC-Aktualisierung**:
       - `open`: Erster Preis im Intervall (wird nur einmal gesetzt)
       - `high`: Höchster Preis (wird mit `max()` aktualisiert)
       - `low`: Niedrigster Preis (wird mit `min()` aktualisiert)
       - `close`: Letzter Preis (wird bei jedem Trade überschrieben)
    
    3. **Volumen-Akkumulation**:
       - `volume_sol += solAmount` (Gesamt-Volumen)
       - `buy_volume_sol += solAmount` (wenn `txType == "buy"`)
       - `sell_volume_sol += solAmount` (wenn `txType == "sell"`)
    
    4. **Trade-Zählung**:
       - `num_buys += 1` (wenn Buy)
       - `num_sells += 1` (wenn Sell)
    
    5. **Weitere Metriken**:
       - `max_single_buy_sol = max(max_single_buy_sol, solAmount)` (größter Buy)
       - `max_single_sell_sol = max(max_single_sell_sol, solAmount)` (größter Sell)
       - `micro_trades += 1` (wenn `solAmount < 0.01`)
       - `wallets.add(traderPublicKey)` (einzigartige Wallets)
    
    6. **Aktuelle Werte**:
       - `v_sol = vSolInBondingCurve` (aktuelles virtuelles SOL)
       - `mcap = price * 1_000_000_000` (angenommene Market Cap)
    
    **Was wird gefüllt:**
    - **Buffer** für jeden Coin (im Speicher, noch nicht in DB)
    - Alle Metriken werden **akkumuliert** bis zum nächsten Flush
    """)
    
    st.markdown("""
    ### Schritt 3: Lifecycle-Checks & Phasen-Management (bei jedem Flush)
    
    **Was wird geprüft:**
    
    1. **Graduierung-Check**:
       ```python
       bonding_pct = (v_sol / SOL_RESERVES_FULL) * 100
       if bonding_pct >= 99.5:
           # Coin graduiert zu Raydium
           stop_tracking(mint, is_graduation=True)
       ```
       - **Berechnung**: Aktuelles virtuelles SOL / 85.0 SOL * 100
       - **Aktion**: Tracking wird beendet, `coin_streams.is_graduated = TRUE`, `current_phase_id = 100`
    
    2. **Phasen-Upgrade-Check**:
       ```python
       age_minutes = (jetzt - token_created_at) - AGE_CALCULATION_OFFSET_MIN
       if age_minutes > phase_cfg["max_age"]:
           # Upgrade zur nächsten Phase
           switch_phase(mint, old_phase, new_phase)
       ```
       - **Berechnung**: Coin-Alter in Minuten (mit Offset)
       - **Aktion**: `coin_streams.current_phase_id` wird aktualisiert
       - **Neues Intervall**: Wird aus der neuen Phase geladen
    
    3. **Lifecycle-Ende-Check**:
       - Wenn keine höhere Phase existiert → Tracking beendet
       - `coin_streams.is_active = FALSE`, `current_phase_id = 99`
    """)
    
    st.markdown("""
    ### Schritt 4: Metrik-Flush (periodisch, basierend auf Phase)
    
    **Wann wird geflusht:**
    - Wenn `now_ts >= entry["next_flush"]` (Intervall abgelaufen)
    - Intervall hängt von der Phase ab (5s, 30s, 60s)
    
    **Was wird berechnet vor dem Speichern:**
    
    1. **Bonding Curve Prozentsatz**:
       ```python
       bonding_curve_pct = (v_sol / SOL_RESERVES_FULL) * 100
       ```
       - **Beispiel**: 42.5 SOL / 85.0 SOL * 100 = 50%
    
    2. **King of the Hill (KOTH)**:
       ```python
       is_koth = market_cap_close > 30000  # SOL
       ```
       - **Bedingung**: Market Cap > 30.000 SOL
       - **Bedeutung**: Coin erscheint in Pump.fun "King of the Hill" Liste
    
    3. **Timestamp**:
       - `timestamp = datetime.now(GERMAN_TZ)` (Berliner Zeit)
       - Wird für jeden Metrik-Eintrag gesetzt
    
    **Was wird in die Datenbank geschrieben:**
    
    ```sql
    INSERT INTO coin_metrics (
        mint,                    -- Token-Adresse
        timestamp,               -- Zeitpunkt (Berlin)
        phase_id_at_time,        -- Phase zum Zeitpunkt
        
        -- OHLC Preise
        price_open,              -- Erster Preis im Intervall
        price_high,              -- Höchster Preis
        price_low,               -- Niedrigster Preis
        price_close,             -- Letzter Preis
        market_cap_close,        -- Market Cap (price * 1B)
        
        -- Bonding Curve
        bonding_curve_pct,       -- Prozentsatz (v_sol / 85.0 * 100)
        virtual_sol_reserves,   -- Aktuelles v_sol
        is_koth,                -- Market Cap > 30k SOL
        
        -- Volumen
        volume_sol,             -- Gesamt-Volumen
        buy_volume_sol,         -- Nur Buy-Volumen
        sell_volume_sol,        -- Nur Sell-Volumen
        
        -- Trade-Struktur
        num_buys,               -- Anzahl Buy-Trades
        num_sells,              -- Anzahl Sell-Trades
        unique_wallets,         -- Anzahl verschiedener Wallets
        num_micro_trades,       -- Trades < 0.01 SOL
        
        -- Whale Watching
        dev_sold_amount,        -- Aktuell 0 (nicht implementiert)
        max_single_buy_sol,     -- Größter einzelner Buy
        max_single_sell_sol     -- Größter einzelner Sell
    ) VALUES (...);
    ```
    
    **Nach dem Speichern:**
    - Buffer wird zurückgesetzt: `entry["buffer"] = get_empty_buffer()`
    - Nächstes Flush-Zeitpunkt wird gesetzt: `entry["next_flush"] = now_ts + interval`
    """)
    
    st.subheader("📊 Was wird aktualisiert?")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        **coin_streams Tabelle:**
        - `current_phase_id` → Bei Phasen-Upgrade
        - `is_active` → Bei Tracking-Ende (FALSE)
        - `is_graduated` → Bei Graduierung (TRUE)
        
        **Aktualisiert durch:**
        - `switch_phase()` → Phase-Upgrade
        - `stop_tracking()` → Tracking-Ende
        """)
    
    with col2:
        st.markdown("""
        **coin_metrics Tabelle:**
        - **Neue Einträge** werden hinzugefügt (keine Updates)
        - Jeder Eintrag = Ein Zeitintervall für einen Coin
        - Mehrere Einträge pro Coin (einer pro Intervall)
        
        **Häufigkeit:**
        - Phase 1: Alle 5 Sekunden
        - Phase 2: Alle 30 Sekunden
        - Phase 3: Alle 60 Sekunden
        """)
    
    st.subheader("🔄 Kontinuierlicher Prozess")
    
    st.markdown("""
    Der Prozess läuft in einer **Endlosschleife**:
    
    ```
    1. DB-Abfrage (alle 10s) → Neue Coins finden
    2. WebSocket-Subscription → Trades abonnieren
    3. Trade-Empfang → Sofort verarbeiten
    4. Buffer-Aktualisierung → Metriken sammeln
    5. Lifecycle-Checks → Phasen & Graduierung prüfen
    6. Flush (wenn Intervall abgelaufen) → In DB speichern
    7. Zurück zu Schritt 3
    ```
    
    **Parallel dazu:**
    - Health-Check Server läuft (Port 8000)
    - Prometheus Metrics werden aktualisiert
    - Logs werden geschrieben
    """)
    
    st.success("""
    ✅ **Zusammenfassung**: Das pump-metric Skript sammelt kontinuierlich Trade-Daten, berechnet Metriken 
    in Echtzeit, verwaltet Phasen-Upgrades automatisch und speichert alles periodisch in die Datenbank. 
    Es aktualisiert sowohl `coin_streams` (Status) als auch `coin_metrics` (Metriken).
    """)
    
    st.divider()
    
    st.header("🔒 11. Lücken-Prävention & Datenintegrität")
    
    st.markdown("""
    Um sicherzustellen, dass **keine Lücken** zwischen Coin-Discovery und Metric-Tracking entstehen, 
    wurden mehrere Sicherheitsmechanismen implementiert:
    """)
    
    st.subheader("🛡️ Automatischer Trigger")
    
    st.markdown("""
    **SQL-Trigger** (`ensure_coin_stream()`):
    - Wird **automatisch** bei jedem INSERT in `discovered_coins` ausgelöst
    - Erstellt **sofort** einen Eintrag in `coin_streams`
    - Läuft **atomar** (in derselben Transaktion)
    - **100% sicher** - keine manuelle Aktion erforderlich
    
    ```sql
    CREATE TRIGGER trigger_ensure_coin_stream
        AFTER INSERT ON discovered_coins
        FOR EACH ROW
        EXECUTE FUNCTION ensure_coin_stream();
    ```
    
    **Was passiert:**
    1. Coin wird in `discovered_coins` eingefügt (von n8n)
    2. Trigger wird automatisch ausgelöst
    3. Stream wird in `coin_streams` erstellt
    4. **Keine Lücke möglich!**
    """)
    
    st.subheader("🔧 Automatische Reparatur")
    
    st.markdown("""
    **Im Tracker integriert:**
    - Bei jeder DB-Abfrage (alle 10 Sekunden) wird `repair_missing_streams()` aufgerufen
    - Findet alle Coins ohne Stream
    - Erstellt fehlende Streams nachträglich
    - **Fallback-Sicherheit** falls Trigger versagt
    
    **Funktion:**
    ```sql
    SELECT repair_missing_streams();
    ```
    
    Gibt zurück: Liste aller erstellten Streams
    """)
    
    st.subheader("📊 Monitoring & Lücken-Erkennung")
    
    st.markdown("""
    **Automatische Prüfung:**
    - Tracker prüft alle 60 Sekunden auf Lücken
    - Verwendet `check_stream_gaps()` Funktion
    - Loggt Warnung wenn Lücken gefunden werden
    
    **Manuelle Prüfung:**
    ```sql
    SELECT * FROM check_stream_gaps();
    ```
    
    **Gibt zurück:**
    - `missing_streams_count`: Anzahl fehlender Streams
    - `coins_without_streams`: Liste der betroffenen Coins
    - `oldest_missing_coin`: Ältester Coin ohne Stream
    - `newest_missing_coin`: Neuester Coin ohne Stream
    """)
    
    st.subheader("⚡ Schnellstart für neue Coins")
    
    st.markdown("""
    **Workflow ohne Lücken:**
    
    1. **Coin Discovery** (pump-discover):
       - WebSocket empfängt neuen Coin
       - n8n verarbeitet und filtert
       - INSERT in `discovered_coins`
       - **Trigger erstellt automatisch Stream** ✅
    
    2. **Stream Aktivierung**:
       - Stream existiert bereits (durch Trigger)
       - `is_active = TRUE` (Standard)
       - `current_phase_id = 1` (Standard)
    
    3. **Metric Tracking** (pump-metric):
       - Tracker fragt DB ab (alle 10s)
       - Findet neuen Stream
       - Abonniert Trades sofort
       - **Keine Verzögerung!**
    """)
    
    st.subheader("🔍 Installation der Sicherheits-Funktionen")
    
    st.code("""
    -- Führe das SQL-Skript aus:
    psql -d crypto -f sql/ensure_streams.sql
    
    -- Oder direkt in der Datenbank:
    \\i sql/ensure_streams.sql
    """, language="bash")
    
    st.info("""
    💡 **Wichtig**: Die Trigger-Funktionen müssen **einmalig** in der Datenbank installiert werden. 
    Danach laufen sie vollautomatisch und garantieren 100%ige Datenintegrität.
    """)
    
    st.warning("""
    ⚠️ **Ohne Trigger**: Wenn der Trigger nicht installiert ist, können Lücken entstehen. 
    Der Tracker repariert diese automatisch, aber es kann zu kurzen Verzögerungen kommen.
    """)
    
    st.divider()
    
    st.header("🛡️ 0. Lücken-Prävention: Universal Trade Buffer (180 Sekunden)")
    
    st.markdown("""
    Um sicherzustellen, dass **keine Trades verloren gehen**, auch wenn ein Coin erst mit Verzögerung aktiviert wird, 
    verwendet das System einen **Universal Trade Buffer** mit einer Dauer von **180 Sekunden (3 Minuten)**.
    """)
    
    st.subheader("🔍 Problem: Verpasste Trades bei verzögerter Aktivierung")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        **Ohne Buffer**:
        ```
        Zeitpunkt 0s:  Coin wird erstellt
        Zeitpunkt 5s:  Erste Trades passieren
        Zeitpunkt 10s: Weitere Trades passieren
        Zeitpunkt 40s: Coin wird in coin_streams aktiviert
        Zeitpunkt 40s: Tracking beginnt → Trades von 5s-40s sind VERLOREN ❌
        ```
        """)
    
    with col2:
        st.markdown("""
        **Mit 180s Buffer**:
        ```
        Zeitpunkt 0s:  Coin wird erstellt
        Zeitpunkt 5s:  Erste Trades → im Buffer gespeichert ✅
        Zeitpunkt 10s: Weitere Trades → im Buffer gespeichert ✅
        Zeitpunkt 40s: Coin wird aktiviert
        Zeitpunkt 40s: Buffer wird rückwirkend verarbeitet ✅
        Zeitpunkt 40s: Alle Trades von 0s-40s werden verarbeitet ✅
        ```
        """)
    
    st.subheader("🔧 Lösung: Zwei parallele WebSocket-Streams")
    
    st.markdown("""
    Das System verwendet **zwei parallele WebSocket-Verbindungen**:
    """)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        ### Stream 1: NewToken-Listener
        - **Methode**: `subscribeNewToken`
        - **Zweck**: Erkennt neue Coins **sofort** bei Erstellung
        - **Reaktion**: 
          - Coin wird **sofort** zum Trade-Stream abonniert
          - Alle Trades werden in den 180s-Buffer gespeichert
        
        **Code**:
        ```python
        # NewToken-Listener erkennt neuen Coin
        if data.get("txType") == "create":
            mint = data["mint"]
            # Sofort abonnieren
            await subscribe_queue.put(mint)
            self.early_subscribed_mints.add(mint)
        ```
        """)
    
    with col2:
        st.markdown("""
        ### Stream 2: Trade-Stream
        - **Methode**: `subscribeTokenTrade`
        - **Zweck**: Empfängt Trade-Events für abonnierte Coins
        - **Funktion**:
          - Empfängt alle Trades für abonnierte Coins
          - Speichert **jeden Trade** im 180s-Buffer
          - Verarbeitet Trades für aktivierte Coins sofort
        
        **Code**:
        ```python
        # Jeder Trade wird im Buffer gespeichert
        self.add_trade_to_buffer(data)
        
        # Wenn Coin aktiv ist, wird Trade sofort verarbeitet
        if data["mint"] in self.watchlist:
            self.process_trade(data)
        ```
        """)
    
    st.subheader("💾 Universal Trade Buffer (180 Sekunden)")
    
    st.markdown("""
    **Struktur**: `{mint: [(timestamp, trade_data), ...]}`
    
    **Eigenschaften**:
    - **Dauer**: 180 Sekunden (3 Minuten) - konfigurierbar über `TRADE_BUFFER_SECONDS`
    - **Größe**: Max. 5000 Trades pro Coin (verhindert Speicher-Überlauf)
    - **Cleanup**: Alte Trades (> 180s) werden automatisch alle 10 Sekunden entfernt
    - **Speicherung**: Alle empfangenen Trades werden mit Timestamp gespeichert
    """)
    
    st.code("""
    def add_trade_to_buffer(self, data):
        mint = data.get("mint")
        if not mint:
            return
        
        if mint not in self.trade_buffer:
            self.trade_buffer[mint] = []
        
        # Speichere Trade mit Timestamp
        trade_entry = (time.time(), data)
        self.trade_buffer[mint].append(trade_entry)
        
        # Begrenze Buffer-Größe (max 5000 Trades)
        if len(self.trade_buffer[mint]) > 5000:
            self.trade_buffer[mint] = self.trade_buffer[mint][-5000:]
    """, language="python")
    
    st.subheader("🔄 Rückwirkende Verarbeitung bei Stream-Aktivierung")
    
    st.markdown("""
    Wenn ein Coin in `coin_streams` aktiviert wird (`is_active = TRUE`), prüft das System den Buffer:
    """)
    
    st.code("""
    # Bei Stream-Aktivierung
    if mint in self.early_subscribed_mints or mint in self.trade_buffer:
        # Zeitfenster für rückwirkende Verarbeitung
        created_at = coin.token_created_at  # Wann wurde Coin erstellt?
        started_at = coin.started_at        # Wann wurde Tracking gestartet?
        now_ts = time.time()
        
        # Finde alle relevanten Trades im Buffer
        cutoff_ts = max(created_at.timestamp(), now_ts - TRADE_BUFFER_SECONDS)
        end_ts = now_ts  # Alle Trades bis jetzt
        
        relevant_trades = []
        for (trade_ts, trade_data) in self.trade_buffer[mint]:
            if cutoff_ts <= trade_ts <= end_ts:
                relevant_trades.append((trade_ts, trade_data))
        
        # Verarbeite Trades rückwirkend (chronologisch)
        relevant_trades.sort(key=lambda x: x[0])  # Sortiere nach Timestamp
        for trade_ts, trade_data in relevant_trades:
            self.process_trade(trade_data)  # Fügt Trade zu Coin-Buffer hinzu
        
        # Metriken werden sofort berechnet und gespeichert
    """, language="python")
    
    st.info("""
    💡 **Wichtig**: 
    - Der Universal Buffer speichert **alle Trades** für 180 Sekunden
    - Bei Stream-Aktivierung werden **verpasste Trades rückwirkend verarbeitet**
    - **Keine Trades gehen verloren**, auch bei Verzögerungen bis zu 180 Sekunden
    - Die Buffer-Dauer kann über `TRADE_BUFFER_SECONDS` angepasst werden (Standard: 180s)
    """)
    
    st.warning("""
    ⚠️ **Grenzen**: 
    - Trades die **vor** der Coin-Erstellung passieren, können nicht erfasst werden (unmöglich)
    - Trades die **mehr als 180 Sekunden** vor der Aktivierung passieren, gehen verloren
    - Bei sehr langen Verzögerungen (> 180s) können frühe Trades fehlen
    """)
    
    st.subheader("📊 Buffer-Statistiken")
    
    st.markdown("""
    Die Buffer-Statistiken werden im Health-Check-Endpoint bereitgestellt:
    
    - `buffer_stats.total_trades_in_buffer`: Gesamtanzahl Trades im Buffer
    - `buffer_stats.coins_with_buffer`: Anzahl Coins mit Trades im Buffer
    - `buffer_stats.buffer_details`: Top 10 Coins mit meisten Trades im Buffer
    
    **Prometheus-Metriken**:
    - `tracker_trade_buffer_size`: Aktuelle Buffer-Größe (Anzahl Coins)
    - `tracker_buffer_trades_total`: Gesamtanzahl Trades die im Buffer gespeichert wurden
    - `tracker_trades_from_buffer_total`: Anzahl Trades die aus dem Buffer verarbeitet wurden
    """)
    
    st.divider()
    
    st.header("📡 1. Datenquelle (für Tracking)")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        ### WebSocket-Verbindung
        - **Quelle**: `wss://pumpportal.fun/api/data`
        - **Protokoll**: WebSocket (Real-Time)
        - **Daten**: Live Trade-Events für getrackte Coins
        """)
    
    with col2:
        st.markdown("""
        ### Trade-Daten
        Jeder Trade enthält:
        - `mint`: Token-Adresse
        - `txType`: "buy" oder "sell"
        - `solAmount`: SOL-Betrag
        - `vSolInBondingCurve`: Virtuelles SOL
        - `vTokensInBondingCurve`: Virtuelle Tokens
        - `traderPublicKey`: Wallet-Adresse
        """)
    
    st.divider()
    
    st.header("🔄 2. Coin-Tracking Prozess (Start)")
    
    st.markdown("""
    ### Schritt 1: Coin-Identifikation aus Datenbank
    - Alle 10 Sekunden wird die Datenbank abgefragt
    - Es werden alle aktiven Coins aus `coin_streams` geladen (wo `is_active = TRUE`)
    - Diese Coins wurden vorher im **Discovery-Prozess** erstellt
    - Für jeden neuen Coin wird ein WebSocket-Subscription erstellt
    
    ### Schritt 2: Trade-Abonnement
    - Der Tracker sendet: `{"method": "subscribeTokenTrade", "keys": [mint1, mint2, ...]}`
    - Ab diesem Zeitpunkt werden alle Trades für diese Coins empfangen
    - **Wichtig**: Nur Coins, die bereits in `coin_streams` existieren, werden getrackt
    """)
    
    st.divider()
    
    st.header("💾 3. Buffer-System & Daten-Sammlung")
    
    st.markdown("""
    Das System verwendet ein **zweistufiges Buffer-System** um sicherzustellen, dass **keine Trades verloren gehen**, 
    auch wenn ein Coin erst mit Verzögerung aktiviert wird.
    """)
    
    st.subheader("🔄 Universal Trade Buffer (180 Sekunden)")
    
    st.markdown("""
    **Problem**: Wenn ein Coin erst nach seiner Erstellung in `coin_streams` aktiviert wird, gehen die ersten Trades verloren.
    
    **Lösung**: Ein **Universal Trade Buffer** speichert **alle empfangenen Trades für 180 Sekunden (3 Minuten)** im Speicher.
    """)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        ### NewToken-Listener Stream
        - **Zweiter WebSocket-Stream** parallel zum Trade-Stream
        - **Methode**: `subscribeNewToken`
        - **Funktion**: Erkennt neue Coins **sofort** bei Erstellung
        - **Reaktion**: Abonniert den Coin **sofort** für Trade-Events
        
        **Ablauf**:
        1. Neuer Coin wird erkannt über `subscribeNewToken`
        2. Coin wird **sofort** zum Trade-Stream abonniert
        3. Alle Trades werden in den 180s-Buffer gespeichert
        4. Wenn Coin in `coin_streams` aktiviert wird → Buffer wird rückwirkend verarbeitet
        """)
    
    with col2:
        st.markdown("""
        ### Trade-Buffer (Ring-Buffer)
        - **Dauer**: 180 Sekunden (3 Minuten)
        - **Struktur**: `{mint: [(timestamp, trade_data), ...]}`
        - **Größe**: Max. 5000 Trades pro Coin
        - **Cleanup**: Alte Trades (> 180s) werden automatisch entfernt
        
        **Speicherung**:
        - Jeder empfangene Trade wird mit Timestamp gespeichert
        - Buffer wird alle 10 Sekunden aufgeräumt
        - Nur Trades der letzten 180 Sekunden werden behalten
        """)
    
    st.subheader("🔄 Rückwirkende Verarbeitung")
    
    st.markdown("""
    Wenn ein Coin in `coin_streams` aktiviert wird, prüft das System den Buffer:
    """)
    
    st.code("""
    # Zeitfenster für rückwirkende Verarbeitung
    created_at = coin.token_created_at  # Wann wurde der Coin erstellt?
    started_at = coin.started_at        # Wann wurde das Tracking gestartet?
    
    # Finde alle Trades im Buffer zwischen created_at und started_at
    relevant_trades = []
    for (trade_timestamp, trade_data) in trade_buffer[mint]:
        if created_at <= trade_timestamp <= started_at:
            relevant_trades.append(trade_data)
    
    # Verarbeite diese Trades rückwirkend
    for trade in relevant_trades:
        process_trade(trade)  # Fügt Trade zu Coin-Buffer hinzu
    """, language="python")
    
    st.info("""
    💡 **Wichtig**: 
    - Der Universal Buffer speichert **alle Trades** für 180 Sekunden
    - Bei Stream-Aktivierung werden **verpasste Trades rückwirkend verarbeitet**
    - **Keine Trades gehen verloren**, auch bei Verzögerungen bis zu 180 Sekunden
    """)
    
    st.subheader("📊 Coin-spezifischer Buffer (für Metriken)")
    
    st.markdown("""
    **Zusätzlich** zum Universal Buffer hat jeder Coin einen **eigenen Buffer** für Metriken-Sammlung:
    
    Für jeden Coin wird ein **Buffer** erstellt, der alle Trades innerhalb eines Zeitintervalls sammelt.
    Das Intervall hängt von der **Phase** des Coins ab (siehe Phasen-Management).
    """)
    
    st.subheader("📊 Gesammelte Daten pro Trade")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        **Preis-Daten (OHLC)**:
        - `open`: Erster Preis im Intervall
        - `high`: Höchster Preis
        - `low`: Niedrigster Preis  
        - `close`: Letzter Preis
        
        **Berechnung**:
        ```
        price = vSolInBondingCurve / vTokensInBondingCurve
        ```
        """)
    
    with col2:
        st.markdown("""
        **Volumen-Daten**:
        - `volume_sol`: Gesamt-Volumen (SOL)
        - `buy_volume_sol`: Nur Buy-Volumen
        - `sell_volume_sol`: Nur Sell-Volumen
        
        **Trade-Zählung**:
        - `num_buys`: Anzahl Buy-Trades
        - `num_sells`: Anzahl Sell-Trades
        """)
    
    st.markdown("""
    ### Weitere gesammelte Metriken
    
    - **Unique Wallets**: Anzahl verschiedener Trader (aus `traderPublicKey`)
    - **Micro Trades**: Trades < 0.01 SOL (mögliche Bot-Aktivität)
    - **Max Single Buy/Sell**: Größter einzelner Trade
    - **Virtual SOL Reserves**: Aktueller Stand der Bonding Curve
    - **Market Cap**: `price * 1_000_000_000` (angenommene Token-Supply)
    """)
    
    st.divider()
    
    st.header("⏱️ 4. Phasen-Management & Intervall-System")
    
    st.markdown("""
    Jeder Coin durchläuft verschiedene **Phasen** basierend auf seinem Alter. Die Phasen werden aus 
    der Tabelle `ref_coin_phases` geladen.
    """)
    
    st.subheader("📋 Standard-Phasen (aus ref_coin_phases)")
    
    st.markdown("""
    | Phase ID | Name | Intervall | Min Alter | Max Alter | Beschreibung |
    |----------|------|-----------|-----------|-----------|--------------|
    | 1 | Baby Zone | 5s | 0 Min | 10 Min | Sehr junge Coins, häufige Updates |
    | 2 | Survival Zone | 30s | 10 Min | 60 Min | Coins die überlebt haben, moderate Updates |
    | 3 | Mature Zone | 60s | 60 Min | 1440 Min (24h) | Reife Coins, weniger häufige Updates |
    | 99 | Finished | 0s | 24h+ | ∞ | Tracking beendet (zu alt) |
    | 100 | Graduated | 0s | 24h+ | ∞ | Zu Raydium graduiert |
    """)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        ### Phasen-Upgrade
        - **Bedingung**: Coin-Alter > `max_age_minutes` der aktuellen Phase
        - **Berechnung**: 
          ```
          age_minutes = (jetzt - token_created_at) - AGE_CALCULATION_OFFSET_MIN
          ```
        - **Offset**: Standard 60 Minuten (konfigurierbar)
        - **Prozess**: Automatisches Upgrade zur nächsten Phase
        """)
    
    with col2:
        st.markdown("""
        ### Intervall-System
        - Jede Phase hat ein `interval_seconds`
        - Metriken werden alle `interval_seconds` gespeichert
        - **Beispiel**: 
          - Phase 1: Alle 5 Sekunden
          - Phase 2: Alle 30 Sekunden
          - Phase 3: Alle 60 Sekunden
        - Je älter der Coin, desto seltener die Updates
        """)
    
    st.info("""
    💡 **Wichtig**: 
    - Wenn ein Coin zu alt für seine Phase wird, wird er automatisch zur nächsten Phase upgegradet
    - Wenn keine höhere Phase existiert (oder Phase ≥ 99), wird das Tracking beendet
    - Die Phasen-Konfiguration kann in der Datenbank angepasst werden (`ref_coin_phases`)
    """)
    
    st.divider()
    
    st.header("🎓 5. Graduierung & Lifecycle-Ende")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        ### Graduierung (zu Raydium)
        - **Bedingung**: Bonding Curve ≥ 99.5%
        - **Berechnung**:
          ```
          bonding_pct = (v_sol / SOL_RESERVES_FULL) * 100
          ```
        - **SOL_RESERVES_FULL**: Standard 85.0 SOL
        - **Ergebnis**: Coin geht zu Raydium, Tracking wird beendet
        """)
    
    with col2:
        st.markdown("""
        ### Lifecycle-Ende
        - **Bedingung**: Coin ist zu alt für alle Phasen
        - **Ergebnis**: Tracking wird beendet, `is_active = FALSE`
        - **Finale Phase**: 99 (beendet) oder 100 (graduiert)
        """)
    
    st.divider()
    
    st.header("📈 6. Metriken-Berechnung vor Speicherung")
    
    st.markdown("""
    Bevor die Daten in die `coin_metrics` Tabelle geschrieben werden, werden folgende Berechnungen durchgeführt:
    """)
    
    st.subheader("Bonding Curve Prozentsatz")
    st.code("""
bonding_curve_pct = (virtual_sol_reserves / SOL_RESERVES_FULL) * 100
    """, language="python")
    
    st.subheader("King of the Hill (KOTH)")
    st.code("""
is_koth = market_cap_close > 30000  # SOL
    """, language="python")
    
    st.markdown("""
    **KOTH** bedeutet, dass der Coin eine Market Cap von über 30.000 SOL hat und damit 
    in der Pump.fun "King of the Hill" Liste erscheint (Sichtbarkeits-Boost).
    """)
    
    st.subheader("Erweiterte Metriken (Neu)")
    
    st.markdown("""
    Zusätzlich werden folgende erweiterte Metriken berechnet:
    """)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.code("""
# Netto-Volumen (Delta)
net_volume_sol = buy_volume_sol - sell_volume_sol

# Volatilität
if price_open > 0:
    volatility_pct = ((price_high - price_low) / price_open) * 100
else:
    volatility_pct = 0.0

# Durchschnittliche Trade-Größe
total_trades = num_buys + num_sells
if total_trades > 0:
    avg_trade_size_sol = volume_sol / total_trades
else:
    avg_trade_size_sol = 0.0
        """, language="python")
    
    with col2:
        st.code("""
# Whale-Tracking (während process_trade)
if sol_amount >= WHALE_THRESHOLD_SOL:  # Standard: 1.0 SOL
    if is_buy:
        whale_buy_volume_sol += sol_amount
        num_whale_buys += 1
    else:
        whale_sell_volume_sol += sol_amount
        num_whale_sells += 1
        """, language="python")
    
    st.info("""
    💡 **Wichtig**: 
    - Alle Berechnungen basieren auf **echten Trade-Daten** aus dem Buffer
    - Keine erfundenen Zahlen - alle Werte werden aus tatsächlichen Trades berechnet
    - Edge Cases werden korrekt behandelt (Division durch 0, etc.)
    """)
    
    st.divider()
    
    st.header("💾 7. Datenbank-Speicherung")
    
    st.markdown("""
    Alle gesammelten Metriken werden in die Tabelle `coin_metrics` geschrieben:
    """)
    
    st.subheader("Gespeicherte Felder")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        **Identifikation**:
        - `mint`: Token-Adresse
        - `timestamp`: Zeitpunkt (Berliner Zeit)
        - `phase_id_at_time`: Phase zum Zeitpunkt
        
        **Preis & Bewertung**:
        - `price_open`
        - `price_high`
        - `price_low`
        - `price_close`
        - `market_cap_close`
        """)
    
    with col2:
        st.markdown("""
        **Pump.fun Mechanik**:
        - `bonding_curve_pct`
        - `virtual_sol_reserves`
        - `is_koth`
        
        **Volumen & Fluss**:
        - `volume_sol`
        - `buy_volume_sol`
        - `sell_volume_sol`
        """)
    
    with col3:
        st.markdown("""
        **Order-Struktur**:
        - `num_buys`
        - `num_sells`
        - `unique_wallets`
        - `num_micro_trades`
        
        **Whale Watching**:
        - `max_single_buy_sol`
        - `max_single_sell_sol`
        - `dev_sold_amount` (aktuell 0)
        
        **Erweiterte Metriken (NEU)**:
        - `net_volume_sol`: Netto-Volumen (Delta: Buy - Sell)
        - `volatility_pct`: Volatilität in Prozent
        - `avg_trade_size_sol`: Durchschnittliche Trade-Größe
        - `whale_buy_volume_sol`: Whale-Buy-Volumen (Trades >= 1.0 SOL)
        - `whale_sell_volume_sol`: Whale-Sell-Volumen
        - `num_whale_buys`: Anzahl Whale-Buys
        - `num_whale_sells`: Anzahl Whale-Sells
        - `buy_pressure_ratio`: Buy-Volumen-Verhältnis [0.0-1.0]
        - `unique_signer_ratio`: Unique-Wallet-Verhältnis [0.0-1.0]
        
        **KRITISCH - Dev-Tracking**:
        - `dev_sold_amount`: **JETZT IMPLEMENTIERT!** Verkauftes Volumen vom Creator (Rug-Pull-Erkennung)
        """)
    
    st.divider()
    
    st.header("📊 8. Erweiterte Metriken (Neu)")
    
    st.markdown("""
    Seit der letzten Erweiterung werden zusätzliche Metriken berechnet, die tiefere Einblicke in das Trade-Verhalten geben:
    """)
    
    st.subheader("💰 Netto-Volumen (Delta)")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        **Berechnung**:
        ```
        net_volume_sol = buy_volume_sol - sell_volume_sol
        ```
        
        **Interpretation**:
        - **Positiv**: Mehr Kaufdruck als Verkaufsdruck
        - **Negativ**: Mehr Verkaufsdruck als Kaufdruck
        - **0**: Ausgewogenes Verhältnis
        """)
    
    with col2:
        st.markdown("""
        **Beispiel**:
        - `buy_volume_sol = 10.5 SOL`
        - `sell_volume_sol = 6.2 SOL`
        - `net_volume_sol = +4.3 SOL` ✅ (Kaufdruck)
        
        **Verwendung**:
        - Identifikation von Bullish/Bearish Trends
        - Erkennung von Verkaufsdruck
        """)
    
    st.subheader("📈 Volatilität")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        **Berechnung**:
        ```
        volatility_pct = ((price_high - price_low) / price_open) * 100
        ```
        
        **Interpretation**:
        - **Niedrig (< 10%)**: Stabile Preise
        - **Mittel (10-30%)**: Normale Schwankungen
        - **Hoch (> 30%)**: Sehr volatile Preise
        """)
    
    with col2:
        st.markdown("""
        **Beispiel**:
        - `price_open = 0.001 SOL`
        - `price_high = 0.0015 SOL`
        - `price_low = 0.0008 SOL`
        - `volatility_pct = 70%` ⚠️ (Sehr volatil)
        
        **Verwendung**:
        - Risiko-Bewertung
        - Erkennung von Pump & Dump
        """)
    
    st.subheader("📊 Durchschnittliche Trade-Größe")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        **Berechnung**:
        ```
        avg_trade_size_sol = volume_sol / (num_buys + num_sells)
        ```
        
        **Interpretation**:
        - **Niedrig (< 0.1 SOL)**: Viele kleine Trades (Retail)
        - **Mittel (0.1-1.0 SOL)**: Gemischte Trader
        - **Hoch (> 1.0 SOL)**: Große Trader (Whales)
        """)
    
    with col2:
        st.markdown("""
        **Beispiel**:
        - `volume_sol = 10.0 SOL`
        - `num_buys + num_sells = 50`
        - `avg_trade_size_sol = 0.2 SOL`
        
        **Verwendung**:
        - Retail vs. Whale-Analyse
        - Identifikation von Bot-Aktivität
        """)
    
    st.subheader("🐋 Whale-Tracking")
    
    st.markdown("""
    **Definition**: Trades mit einem Volumen >= `WHALE_THRESHOLD_SOL` (Standard: 1.0 SOL) werden als "Whale-Trades" klassifiziert.
    """)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        **Buy-Whales**:
        - `whale_buy_volume_sol`: Gesamtvolumen aller Whale-Buys
        - `num_whale_buys`: Anzahl Whale-Buy-Trades
        
        **Interpretation**:
        - Viele Whale-Buys = Institutionelles Interesse
        - Hohes Whale-Volumen = Signifikante Investition
        """)
    
    with col2:
        st.markdown("""
        **Sell-Whales**:
        - `whale_sell_volume_sol`: Gesamtvolumen aller Whale-Sells
        - `num_whale_sells`: Anzahl Whale-Sell-Trades
        
        **Interpretation**:
        - Viele Whale-Sells = Profit-Taking oder Exit
        - Hohes Whale-Sell-Volumen = Signifikante Verkäufe
        """)
    
    st.code("""
    # Whale-Erkennung während Trade-Verarbeitung
    if sol_amount >= WHALE_THRESHOLD_SOL:  # Standard: 1.0 SOL
        if is_buy:
            whale_buy_vol += sol_amount
            num_whale_buys += 1
        else:
            whale_sell_vol += sol_amount
            num_whale_sells += 1
    """, language="python")
    
    st.info("""
    💡 **Wichtig**: 
    - Whale-Tracking erfolgt **während** der Trade-Verarbeitung (kein zusätzlicher Loop)
    - Schwellenwert ist konfigurierbar über `WHALE_THRESHOLD_SOL` (Standard: 1.0 SOL)
    - Alle Werte basieren auf **echten Trade-Daten** (keine erfundenen Zahlen)
    """)
    
    st.subheader("📊 Buy Pressure Ratio")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        **Berechnung**:
        ```
        buy_pressure_ratio = buy_volume / (buy_volume + sell_volume)
        ```
        
        **Interpretation**:
        - **0.0**: Nur Sells (100% Verkaufsdruck)
        - **0.5**: Ausgewogen (50% Buy, 50% Sell)
        - **1.0**: Nur Buys (100% Kaufdruck)
        """)
    
    with col2:
        st.markdown("""
        **Beispiel**:
        - `buy_volume = 10 SOL`
        - `sell_volume = 90 SOL`
        - `buy_pressure_ratio = 0.1` ⚠️ (Starker Verkaufsdruck)
        
        **Warum wichtig**:
        - 10 SOL Buy bei 100 SOL Volumen = 0.1 (schlecht)
        - 10 SOL Buy bei 12 SOL Volumen = 0.83 (gut)
        - Relative Metrik ist aussagekräftiger als absolute Zahlen
        """)
    
    st.subheader("👥 Unique Signer Ratio")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        **Berechnung**:
        ```
        unique_signer_ratio = unique_wallets / (num_buys + num_sells)
        ```
        
        **Interpretation**:
        - **Niedrig (< 0.1)**: Wash-Trading (wenige Wallets, viele Trades)
        - **Mittel (0.1-0.5)**: Gemischte Aktivität
        - **Hoch (> 0.5)**: Organisches Wachstum (viele verschiedene Trader)
        """)
    
    with col2:
        st.markdown("""
        **Beispiel**:
        - `unique_wallets = 2`
        - `total_trades = 100`
        - `unique_signer_ratio = 0.02` ⚠️ (Wash-Trading!)
        
        **Warum wichtig**:
        - Identifikation von Bot-Spam vs. echtem Interesse
        - Niedrige Ratio = Fake-Volumen
        - Hohe Ratio = Organisches Wachstum
        """)
    
    st.subheader("⚠️ Dev-Tracking (KRITISCH für Rug-Pull-Erkennung)")
    
    st.markdown("""
    **Problem**: Wenn der Creator (Developer) seine Tokens verkauft, ist das ein starker Indikator für einen möglichen Rug-Pull.
    
    **Lösung**: Das System prüft bei jedem Sell-Trade, ob die `traderPublicKey` mit der `trader_public_key` aus `discovered_coins` übereinstimmt.
    """)
    
    st.code("""
    # Dev-Wallet-Erkennung während Trade-Verarbeitung
    creator_address = entry["meta"]["creator_address"]  # Aus discovered_coins.trader_public_key
    trader_key = data["traderPublicKey"]
    
    if not is_buy and creator_address and trader_key == creator_address:
        buf["dev_sold_amount"] += sol_amount  # KRITISCH: Dev hat verkauft!
    """, language="python")
    
    st.warning("""
    ⚠️ **KRITISCH**: 
    - `dev_sold_amount` war vorher immer 0 (nicht implementiert)
    - **JETZT IMPLEMENTIERT**: Dev-Verkäufe werden korrekt getrackt
    - Für KI-Modelle ist dies der **wichtigste Indikator** für Rug-Pull-Risiko
    - Wenn `dev_sold_amount > 0`, hat der Creator verkauft → **Höheres Risiko**
    """)
    
    st.info("""
    💡 **Datenquelle**: 
    - Die Creator-Wallet (`trader_public_key`) wird aus `discovered_coins` geladen
    - Bei jedem Sell-Trade wird geprüft: `traderPublicKey == creator_address`
    - Nur Sell-Trades vom Creator werden gezählt (Buy-Trades sind normal)
    """)
    
    st.divider()
    
    st.header("🔄 9. Batch-Verarbeitung")
    
    st.markdown("""
    - Metriken werden **nicht einzeln** gespeichert, sondern in **Batches**
    - Alle Coins, deren Intervall abgelaufen ist, werden zusammen gespeichert
    - Dies erhöht die Performance erheblich
    - Nach dem Speichern wird der Buffer für jeden Coin zurückgesetzt
    """)
    
    st.info("""
    💡 **Beispiel**: Wenn 10 Coins gleichzeitig ihr Intervall erreichen, werden alle 10 Metriken 
    in einer einzigen SQL-Query gespeichert (`executemany`).
    """)
    
    st.divider()
    
    st.header("⚙️ 10. Konfiguration")
    
    st.markdown("""
    Wichtige Konfigurationsparameter (siehe Konfiguration-Tab):
    """)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        **Datenbank**:
        - `DB_REFRESH_INTERVAL`: Wie oft nach neuen Coins gesucht wird (Standard: 10s)
        - `DB_RETRY_DELAY`: Wartezeit bei DB-Fehlern (Standard: 5s)
        - `DB_DSN`: PostgreSQL Connection String
        
        **Bonding Curve**:
        - `SOL_RESERVES_FULL`: SOL für 100% Bonding Curve (Standard: 85.0)
        - `AGE_CALCULATION_OFFSET_MIN`: Offset für Altersberechnung (Standard: 60 Min)
        """)
    
    with col2:
        st.markdown("""
        **WebSocket**:
        - `WS_URI`: WebSocket-Endpunkt (Standard: wss://pumpportal.fun/api/data)
        - `WS_RETRY_DELAY`: Wartezeit bei Reconnect (Standard: 3s)
        - `WS_PING_INTERVAL`: Ping-Intervall (Standard: 20s)
        - `WS_CONNECTION_TIMEOUT`: Timeout für Verbindung (Standard: 30s)
        
        **Buffer & Tracking**:
        - `TRADE_BUFFER_SECONDS`: Buffer-Dauer für verpasste Trades (Standard: 180s = 3 Min)
        - `WHALE_THRESHOLD_SOL`: Schwellenwert für Whale-Trades (Standard: 1.0 SOL)
        """)
    
    st.divider()
    
    st.header("📊 11. Vollständige Metriken-Übersicht")
    
    st.markdown("""
    Die `coin_metrics` Tabelle speichert folgende Metriken für jeden Coin in jedem Intervall:
    """)
    
    st.subheader("📋 Basis-Metriken")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        **Identifikation**:
        - `mint`: Token-Adresse
        - `timestamp`: Zeitpunkt (Berliner Zeit)
        - `phase_id_at_time`: Phase zum Zeitpunkt
        
        **Preis (OHLC)**:
        - `price_open`: Erster Preis
        - `price_high`: Höchster Preis
        - `price_low`: Niedrigster Preis
        - `price_close`: Letzter Preis
        - `market_cap_close`: Market Cap
        """)
    
    with col2:
        st.markdown("""
        **Volumen**:
        - `volume_sol`: Gesamt-Volumen
        - `buy_volume_sol`: Buy-Volumen
        - `sell_volume_sol`: Sell-Volumen
        - `net_volume_sol`: Delta (Buy - Sell)
        
        **Trade-Zählung**:
        - `num_buys`: Anzahl Buys
        - `num_sells`: Anzahl Sells
        - `unique_wallets`: Anzahl unique Wallets
        """)
    
    with col3:
        st.markdown("""
        **Pump.fun Mechanik**:
        - `bonding_curve_pct`: Bonding Curve %
        - `virtual_sol_reserves`: Virtuelles SOL
        - `is_koth`: King of the Hill (MC > 30k)
        
        **Weitere**:
        - `num_micro_trades`: Trades < 0.01 SOL
        - `max_single_buy_sol`: Größter Buy
        - `max_single_sell_sol`: Größter Sell
        """)
    
    st.subheader("🐋 Whale & Erweiterte Metriken")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        **Whale-Tracking** (Trades >= `WHALE_THRESHOLD_SOL`):
        - `whale_buy_volume_sol`: Whale-Buy-Volumen
        - `whale_sell_volume_sol`: Whale-Sell-Volumen
        - `num_whale_buys`: Anzahl Whale-Buys
        - `num_whale_sells`: Anzahl Whale-Sells
        
        **Volatilität & Größe**:
        - `volatility_pct`: Preis-Schwankung %
        - `avg_trade_size_sol`: Durchschnittliche Trade-Größe
        """)
    
    with col2:
        st.markdown("""
        **Ratio-Metriken** (Bot-Spam vs. echtes Interesse):
        - `buy_pressure_ratio`: Buy-Volumen-Verhältnis [0.0-1.0]
          - 0.0 = nur Sells, 1.0 = nur Buys, 0.5 = ausgeglichen
        - `unique_signer_ratio`: Unique-Wallet-Verhältnis [0.0-1.0]
          - Niedrig = Wash-Trading, Hoch = organisches Wachstum
        
        **⚠️ KRITISCH - Rug-Pull-Erkennung**:
        - `dev_sold_amount`: Verkauftes Volumen vom Creator
          - **Wichtigster Indikator** für Rug-Pull-Risiko
          - Wird nur bei Sell-Trades vom Creator gezählt
        """)
    
    st.divider()
    
    st.header("🔍 12. Monitoring & Metriken")
    
    st.markdown("""
    Das System bietet verschiedene Monitoring-Endpunkte und Tools:
    """)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        **API-Endpunkte**:
        - `GET /health`: Health-Check (DB + WebSocket Status)
        - `GET /metrics`: Prometheus-Metriken (für Monitoring)
        
        **Health-Check liefert**:
        - DB-Verbindungsstatus
        - WebSocket-Verbindungsstatus
        - Buffer-Statistiken
        - Uptime & Fehler-Info
        """)
    
    with col2:
        st.markdown("""
        **Web-UI Features**:
        - **Dashboard**: Live-Status, Statistiken, Buffer-Info
        - **Konfiguration**: Einstellungen anpassen (außer Coolify)
        - **Logs**: Live-Logs vom Tracker
        - **Metriken**: Prometheus-Metriken anzeigen
        - **Info**: Diese Dokumentation
        """)
    
    st.subheader("📈 Prometheus-Metriken")
    
    st.markdown("""
    Wichtige Prometheus-Metriken für Monitoring:
    """)
    
    st.code("""
    # Trade-Statistiken
    tracker_trades_received_total      # Gesamt empfangene Trades
    tracker_trades_processed_total     # Gesamt verarbeitete Trades
    tracker_trades_from_buffer_total   # Trades aus Buffer verarbeitet
    tracker_metrics_saved_total        # Gesamt gespeicherte Metriken
    
    # Coin-Statistiken
    tracker_coins_tracked              # Aktuell getrackte Coins
    tracker_coins_graduated_total       # Gesamt graduierte Coins
    tracker_coins_finished_total       # Gesamt beendete Coins
    tracker_phase_switches_total       # Gesamt Phase-Wechsel
    
    # Buffer-System
    tracker_trade_buffer_size          # Anzahl Coins im Buffer
    tracker_buffer_trades_total        # Gesamt Trades im Buffer gespeichert
    
    # Verbindungs-Status
    tracker_ws_connected               # WebSocket verbunden (0/1)
    tracker_db_connected               # DB verbunden (0/1)
    tracker_ws_reconnects_total        # Anzahl Reconnects
    tracker_uptime_seconds             # Uptime in Sekunden
    """, language="text")
    
    st.divider()
    
    st.header("🎯 13. Zusammenfassung & Workflow")
    
    st.markdown("""
    ### Kompletter Datenfluss (von Discovery bis Metriken)
    """)
    
    st.code("""
    1. PUMP-DISCOVER:
       └─> WebSocket: subscribeNewToken
       └─> API: Coin-Metadaten abrufen
       └─> DB: discovered_coins (Coin-Info + trader_public_key)
       └─> DB: coin_streams (Tracking-Status)
    
    2. PUMP-METRIC (dieses System):
       └─> DB: Lade aktive Coins aus coin_streams
       └─> WebSocket: subscribeTokenTrade (für aktive Coins)
       └─> WebSocket: subscribeNewToken (für neue Coins)
       └─> Buffer: Alle Trades für 180s speichern
       └─> Verarbeitung: Trades aggregieren
       └─> Berechnung: Metriken berechnen (inkl. Dev-Tracking, Ratios)
       └─> DB: coin_metrics (alle Metriken speichern)
    """, language="text")
    
    st.markdown("""
    ### Wichtige Features
    """)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        ✅ **Buffer-System**:
        - 180s Universal Trade Buffer
        - Rückwirkende Verarbeitung
        - Keine Trades gehen verloren
        
        ✅ **Dev-Tracking**:
        - Creator-Verkäufe werden getrackt
        - Wichtigster Rug-Pull-Indikator
        - Basierend auf trader_public_key
        """)
    
    with col2:
        st.markdown("""
        ✅ **Erweiterte Metriken**:
        - Whale-Tracking (>= 1.0 SOL)
        - Volatilität & Netto-Volumen
        - Ratio-Metriken (Bot-Spam-Erkennung)
        
        ✅ **Automatisierung**:
        - Phasen-Management
        - Graduation-Erkennung
        - Auto-Reconnect
        """)
    
    st.success("""
    ✅ **Zusammenfassung**: Das System sammelt kontinuierlich Trade-Daten, aggregiert sie in Buffern, 
    berechnet erweiterte Metriken (inkl. Dev-Tracking und Ratios) und speichert sie periodisch in die Datenbank. 
    Alle Prozesse laufen automatisch und erfordern keine manuelle Intervention.
    
    **Für KI-Modelle besonders wichtig**:
    - `dev_sold_amount`: Rug-Pull-Risiko-Indikator
    - `buy_pressure_ratio`: Relatives Buy/Sell-Verhältnis
    - `unique_signer_ratio`: Wash-Trading-Erkennung
    - `whale_*`: Institutionelles Interesse
    - `volatility_pct`: Risiko-Bewertung
    """)
    
    st.divider()
    
    st.header("📚 14. Technische Details")
    
    st.subheader("Datenquellen")
    
    st.markdown("""
    - **WebSocket**: `wss://pumpportal.fun/api/data`
      - `subscribeNewToken`: Neue Coins erkennen
      - `subscribeTokenTrade`: Trade-Events empfangen
    
    - **Datenbank**: PostgreSQL
      - `discovered_coins`: Coin-Metadaten (inkl. `trader_public_key`)
      - `coin_streams`: Tracking-Status
      - `coin_metrics`: Gespeicherte Metriken
      - `ref_coin_phases`: Phasen-Konfiguration
    """)
    
    st.subheader("Performance-Optimierungen")
    
    st.markdown("""
    - **Batch-Inserts**: Metriken werden in Batches gespeichert (nicht einzeln)
    - **Buffer-Cleanup**: Alte Trades werden alle 10s entfernt
    - **DB-Refresh**: Nur alle 10s wird nach neuen Coins gesucht
    - **Gap-Check**: Nur alle 60s wird auf Lücken geprüft
    - **Index**: `idx_metrics_mint_time` für schnelle Abfragen
    """)
    
    st.subheader("Fehlerbehandlung")
    
    st.markdown("""
    - **WebSocket**: Automatischer Reconnect mit exponentieller Backoff
    - **Datenbank**: Retry-Logik mit konfigurierbarer Wartezeit
    - **Fehler-Logging**: Alle Fehler werden geloggt und in Health-Check angezeigt
    - **Graceful Degradation**: System läuft weiter auch bei Teilausfällen
    """)

