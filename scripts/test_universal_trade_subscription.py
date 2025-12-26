#!/usr/bin/env python3
"""
Test-Script: Prüft ob die pumpportal.fun API eine universelle Trade-Subscription unterstützt

Getestete Methoden:
1. subscribeTokenTrade ohne keys
2. subscribeAllTrades
3. subscribeTokenTrade mit leerem Array
4. subscribeTokenTrade mit keys: null
"""

import asyncio
import websockets
import json
import ssl
import time
from datetime import datetime
from collections import defaultdict

async def test_subscription_method(ws, method_name, subscription_payload, test_duration=30):
    """Testet eine Subscription-Methode und zählt empfangene Trades"""
    print(f"\n{'='*80}")
    print(f"🧪 Teste: {method_name}")
    print(f"📤 Sende: {json.dumps(subscription_payload)}")
    print(f"{'='*80}\n")
    
    # Sende Subscription
    await ws.send(json.dumps(subscription_payload))
    
    # Sammle Trades für test_duration Sekunden
    trades_received = []
    coins_seen = set()
    start_time = time.time()
    
    try:
        while time.time() - start_time < test_duration:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(msg)
                
                # Prüfe ob es ein Trade-Event ist
                if "txType" in data and data.get("txType") in ["buy", "sell"]:
                    trades_received.append({
                        "mint": data.get("mint"),
                        "txType": data.get("txType"),
                        "timestamp": datetime.now().isoformat(),
                        "solAmount": data.get("solAmount")
                    })
                    coins_seen.add(data.get("mint"))
                    print(f"✅ Trade empfangen: {data.get('mint', '')[:8]}... | {data.get('txType')} | {data.get('solAmount', 0)} SOL")
                
                # Prüfe ob es ein create-Event ist (neuer Coin)
                elif data.get("txType") == "create":
                    print(f"📦 Neuer Coin: {data.get('name', 'N/A')} ({data.get('symbol', 'N/A')})")
                
                # Prüfe auf Fehlermeldungen
                elif "error" in data or "message" in data:
                    print(f"⚠️  Nachricht: {data.get('error') or data.get('message')}")
                    
            except asyncio.TimeoutError:
                # Timeout ist okay, wir warten weiter
                continue
            except json.JSONDecodeError as e:
                print(f"⚠️  JSON-Fehler: {e}")
                continue
    
    except Exception as e:
        print(f"❌ Fehler während Test: {e}")
    
    # Ergebnis
    print(f"\n📊 Ergebnis für {method_name}:")
    print(f"   - Trades empfangen: {len(trades_received)}")
    print(f"   - Verschiedene Coins: {len(coins_seen)}")
    if trades_received:
        print(f"   - Erste 5 Trades:")
        for trade in trades_received[:5]:
            print(f"     • {trade['mint'][:8]}... | {trade['txType']} | {trade['solAmount']} SOL")
    
    return {
        "method": method_name,
        "payload": subscription_payload,
        "trades_count": len(trades_received),
        "coins_count": len(coins_seen),
        "trades": trades_received[:10],  # Erste 10 für Analyse
        "success": len(trades_received) > 0
    }

async def main():
    """Hauptfunktion: Testet verschiedene Subscription-Methoden"""
    uri = "wss://pumpportal.fun/api/data"
    
    print("🔌 Verbinde zu Pump.fun WebSocket...")
    print("="*80)
    
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    results = []
    
    try:
        async with websockets.connect(
            uri,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=10,
            max_size=2**23,
            ssl=ssl_context
        ) as ws:
            print("✅ Verbunden!\n")
            
            # Test 1: subscribeTokenTrade ohne keys
            result1 = await test_subscription_method(
                ws,
                "subscribeTokenTrade (ohne keys)",
                {"method": "subscribeTokenTrade"},
                test_duration=30
            )
            results.append(result1)
            
            # Warte kurz zwischen Tests
            await asyncio.sleep(2)
            
            # Test 2: subscribeAllTrades
            result2 = await test_subscription_method(
                ws,
                "subscribeAllTrades",
                {"method": "subscribeAllTrades"},
                test_duration=30
            )
            results.append(result2)
            
            # Warte kurz zwischen Tests
            await asyncio.sleep(2)
            
            # Test 3: subscribeTokenTrade mit leerem Array
            result3 = await test_subscription_method(
                ws,
                "subscribeTokenTrade (keys: [])",
                {"method": "subscribeTokenTrade", "keys": []},
                test_duration=30
            )
            results.append(result3)
            
            # Warte kurz zwischen Tests
            await asyncio.sleep(2)
            
            # Test 4: subscribeTokenTrade mit keys: null
            result4 = await test_subscription_method(
                ws,
                "subscribeTokenTrade (keys: null)",
                {"method": "subscribeTokenTrade", "keys": None},
                test_duration=30
            )
            results.append(result4)
            
            # Warte kurz zwischen Tests
            await asyncio.sleep(2)
            
            # Test 5: subscribeAllTokenTrades (alternative Schreibweise)
            result5 = await test_subscription_method(
                ws,
                "subscribeAllTokenTrades",
                {"method": "subscribeAllTokenTrades"},
                test_duration=30
            )
            results.append(result5)
            
    except Exception as e:
        print(f"❌ Verbindungsfehler: {e}")
        return
    
    # Zusammenfassung
    print("\n" + "="*80)
    print("📊 ZUSAMMENFASSUNG")
    print("="*80)
    
    for result in results:
        status = "✅ FUNKTIONIERT" if result["success"] else "❌ FUNKTIONIERT NICHT"
        print(f"\n{status}: {result['method']}")
        print(f"   Trades empfangen: {result['trades_count']}")
        print(f"   Verschiedene Coins: {result['coins_count']}")
        if result['trades_count'] > 0:
            print(f"   ✅ Diese Methode funktioniert! Universelle Trade-Subscription möglich.")
    
    # Empfehlung
    working_methods = [r for r in results if r["success"]]
    if working_methods:
        print(f"\n🎉 ERFOLG: {len(working_methods)} Methode(n) funktionieren!")
        print(f"✅ Empfohlene Methode: {working_methods[0]['method']}")
        print(f"   Payload: {json.dumps(working_methods[0]['payload'])}")
        print(f"\n💡 Diese Methode kann für universelle Trade-Subscription verwendet werden!")
    else:
        print(f"\n❌ KEINE universelle Trade-Subscription verfügbar")
        print(f"💡 Alternative: Alle aktiven Coins vorab abonnieren")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Test abgebrochen")



