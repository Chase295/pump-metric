#!/usr/bin/env python3
"""
Test-Skript für das Buffer-System
Prüft ob das 180s Buffer-System korrekt funktioniert
"""

import requests
import time
import json
from datetime import datetime, timedelta

TRACKER_URL = "http://localhost:8009"

def get_health():
    """Holt Health-Status vom Tracker"""
    try:
        response = requests.get(f"{TRACKER_URL}/health", timeout=5)
        return response.json()
    except Exception as e:
        print(f"❌ Fehler beim Abrufen des Health-Status: {e}")
        return None

def get_metrics():
    """Holt Prometheus-Metriken vom Tracker"""
    try:
        response = requests.get(f"{TRACKER_URL}/metrics", timeout=5)
        return response.text
    except Exception as e:
        print(f"❌ Fehler beim Abrufen der Metriken: {e}")
        return None

def parse_metric(metrics_text, metric_name):
    """Parst eine Prometheus-Metrik"""
    for line in metrics_text.split('\n'):
        if line.startswith(metric_name):
            if ' ' in line:
                value = line.split(' ')[1].strip()
                try:
                    return float(value)
                except:
                    return value
    return None

def test_buffer_system():
    """Testet das Buffer-System"""
    print("=" * 60)
    print("🧪 Buffer-System Test")
    print("=" * 60)
    print()
    
    # 1. Prüfe ob Tracker läuft
    print("1️⃣ Prüfe Tracker-Status...")
    health = get_health()
    if not health:
        print("❌ Tracker ist nicht erreichbar!")
        return False
    
    if health.get("status") != "healthy":
        print(f"⚠️ Tracker-Status: {health.get('status')}")
        print(f"   DB: {health.get('db_connected')}")
        print(f"   WS: {health.get('ws_connected')}")
    else:
        print("✅ Tracker läuft (healthy)")
    
    print()
    
    # 2. Prüfe Buffer-Statistiken
    print("2️⃣ Prüfe Buffer-Statistiken...")
    buffer_stats = health.get("buffer_stats", {})
    
    total_trades = buffer_stats.get("total_trades_in_buffer", 0)
    coins_with_buffer = buffer_stats.get("coins_with_buffer", 0)
    buffer_details = buffer_stats.get("buffer_details", {})
    
    print(f"   📊 Trades im Buffer: {total_trades}")
    print(f"   🪙 Coins mit Buffer: {coins_with_buffer}")
    
    if buffer_details:
        print(f"   📋 Top Coins im Buffer:")
        for coin, count in list(buffer_details.items())[:5]:
            print(f"      - {coin}: {count} Trades")
    else:
        print("   ℹ️  Keine Coins mit Trades im Buffer")
    
    print()
    
    # 3. Prüfe Prometheus-Metriken
    print("3️⃣ Prüfe Prometheus-Metriken...")
    metrics = get_metrics()
    if not metrics:
        print("❌ Metriken konnten nicht abgerufen werden!")
        return False
    
    buffer_size = parse_metric(metrics, "tracker_trade_buffer_size")
    buffer_trades_total = parse_metric(metrics, "tracker_buffer_trades_total")
    trades_from_buffer = parse_metric(metrics, "tracker_trades_from_buffer_total")
    
    print(f"   📦 Buffer-Größe (Coins): {buffer_size}")
    print(f"   💾 Gesamt im Buffer gespeichert: {buffer_trades_total}")
    print(f"   🔄 Aus Buffer verarbeitet: {trades_from_buffer}")
    
    if buffer_trades_total and buffer_trades_total > 0:
        if trades_from_buffer and trades_from_buffer > 0:
            ratio = (trades_from_buffer / buffer_trades_total) * 100
            print(f"   📈 Verarbeitungs-Rate: {ratio:.1f}%")
        else:
            print("   ⚠️  Keine Trades wurden bisher aus dem Buffer verarbeitet")
    
    print()
    
    # 4. Prüfe WebSocket-Status
    print("4️⃣ Prüfe WebSocket-Verbindungen...")
    ws_connected = health.get("ws_connected", False)
    last_message_ago = health.get("last_message_ago")
    
    if ws_connected:
        print("   ✅ Trade-Stream: Verbunden")
    else:
        print("   ❌ Trade-Stream: NICHT verbunden")
    
    if last_message_ago is not None:
        if last_message_ago < 60:
            print(f"   ✅ Letzte Nachricht: vor {last_message_ago}s (OK)")
        else:
            print(f"   ⚠️  Letzte Nachricht: vor {last_message_ago}s (zu alt!)")
    else:
        print("   ⚠️  Keine Nachrichten empfangen")
    
    print()
    
    # 5. Zusammenfassung
    print("=" * 60)
    print("📊 Zusammenfassung")
    print("=" * 60)
    
    issues = []
    
    if not ws_connected:
        issues.append("❌ Trade-Stream ist nicht verbunden")
    
    if buffer_trades_total == 0 or buffer_trades_total is None:
        issues.append("⚠️  Keine Trades wurden im Buffer gespeichert (normal wenn keine neuen Coins)")
    
    if trades_from_buffer == 0 or trades_from_buffer is None:
        issues.append("ℹ️  Keine Trades wurden aus dem Buffer verarbeitet (normal wenn keine Coins aktiviert wurden)")
    
    if total_trades > 1000:
        issues.append(f"⚠️  Viele Trades im Buffer ({total_trades}) - möglicherweise Cleanup-Problem")
    
    if issues:
        print("⚠️  Gefundene Probleme:")
        for issue in issues:
            print(f"   {issue}")
    else:
        print("✅ Alle Checks bestanden!")
        print()
        print("💡 Um das Buffer-System zu testen:")
        print("   1. Warte auf einen neuen Coin (oder aktiviere einen manuell)")
        print("   2. Prüfe ob '🆕 Neuer Coin erkannt' in den Logs erscheint")
        print("   3. Prüfe ob Trades im Buffer gespeichert werden (buffer_trades_total steigt)")
        print("   4. Aktiviere den Coin in coin_streams")
        print("   5. Prüfe ob '🔄 Buffer: X rückwirkende Trades' in den Logs erscheint")
        print("   6. Prüfe ob trades_from_buffer_total steigt")
    
    print()
    return len(issues) == 0

if __name__ == "__main__":
    try:
        success = test_buffer_system()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n👋 Test abgebrochen")
        exit(1)
    except Exception as e:
        print(f"\n❌ Unerwarteter Fehler: {e}")
        import traceback
        traceback.print_exc()
        exit(1)


