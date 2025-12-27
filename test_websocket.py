#!/usr/bin/env python3
"""WebSocket-Verbindungstest"""
import asyncio
import websockets
import json
import sys

WS_URI = "wss://pumpportal.fun/api/data"

async def test_websocket():
    print("=" * 60)
    print("WEBSOCKET-VERBINDUNGSTEST")
    print("=" * 60)
    print(f"URI: {WS_URI}")
    print()
    
    try:
        print("1. Versuche Verbindung herzustellen...")
        async with websockets.connect(
            WS_URI,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=10,
            max_size=2**23,
            compression=None
        ) as ws:
            print("   ✅ WebSocket verbunden!")
            
            print("\n2. Sende Test-Message (subscribeNewToken)...")
            test_msg = {"method": "subscribeNewToken"}
            await ws.send(json.dumps(test_msg))
            print(f"   ✅ Nachricht gesendet: {test_msg}")
            
            print("\n3. Warte auf Antwort (5 Sekunden)...")
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                print(f"   ✅ Antwort erhalten: {msg[:200]}...")
                
                # Versuche JSON zu parsen
                try:
                    data = json.loads(msg)
                    print(f"   ✅ JSON geparst: {json.dumps(data, indent=2)[:300]}...")
                except:
                    print("   ⚠️  Antwort ist kein JSON")
            except asyncio.TimeoutError:
                print("   ⚠️  Keine Antwort innerhalb von 5 Sekunden (kann normal sein)")
            
            print("\n4. Verbindung erfolgreich!")
            return True
            
    except websockets.exceptions.InvalidURI as e:
        print(f"   ❌ Ungültige URI: {e}")
        return False
    except websockets.exceptions.InvalidStatusCode as e:
        print(f"   ❌ Ungültiger Status-Code: {e}")
        return False
    except websockets.exceptions.ConnectionClosed as e:
        print(f"   ❌ Verbindung geschlossen: {e}")
        return False
    except OSError as e:
        print(f"   ❌ Netzwerk-Fehler: {e}")
        print(f"      Fehler-Typ: {type(e).__name__}")
        return False
    except Exception as e:
        print(f"   ❌ Unerwarteter Fehler: {e}")
        print(f"      Fehler-Typ: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    result = asyncio.run(test_websocket())
    print("\n" + "=" * 60)
    if result:
        print("✅ TEST ERFOLGREICH")
    else:
        print("❌ TEST FEHLGESCHLAGEN")
    print("=" * 60)
    sys.exit(0 if result else 1)

