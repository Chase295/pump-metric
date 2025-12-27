#!/usr/bin/env python3
"""Test-Script für ATH-Tracking"""
import asyncio
import asyncpg
import os

DB_DSN = os.getenv("DB_DSN", "postgresql://postgres:9HVxi6hN6j7xpmqUx84o@100.118.155.75:5432/crypto")

async def test_ath():
    conn = await asyncpg.connect(DB_DSN)
    
    print("=" * 60)
    print("ATH-TRACKING TEST")
    print("=" * 60)
    
    # Test 1: Prüfe Spalten
    print("\n1. Prüfe ATH-Spalten:")
    columns = await conn.fetch("""
        SELECT column_name, data_type, column_default
        FROM information_schema.columns 
        WHERE table_name = 'coin_streams' 
        AND column_name IN ('ath_price_sol', 'ath_timestamp')
    """)
    for col in columns:
        print(f"   ✅ {col['column_name']}: {col['data_type']} (Default: {col['column_default']})")
    
    # Test 2: Prüfe Index
    print("\n2. Prüfe ATH-Index:")
    index = await conn.fetchrow("""
        SELECT indexname, indexdef 
        FROM pg_indexes 
        WHERE tablename = 'coin_streams' 
        AND indexname = 'idx_streams_ath_price'
    """)
    if index:
        print(f"   ✅ Index vorhanden: {index['indexname']}")
    else:
        print("   ❌ Index fehlt!")
    
    # Test 3: Statistiken
    print("\n3. ATH-Statistiken:")
    stats = await conn.fetchrow("""
        SELECT 
            COUNT(*) as total_active,
            COUNT(ath_price_sol) as with_ath,
            COUNT(CASE WHEN ath_price_sol > 0 THEN 1 END) as with_positive_ath,
            MAX(ath_price_sol) as max_ath,
            AVG(ath_price_sol) as avg_ath
        FROM coin_streams 
        WHERE is_active = TRUE
    """)
    print(f"   Aktive Coins: {stats['total_active']}")
    print(f"   Mit ATH-Wert: {stats['with_ath']}")
    print(f"   Mit positivem ATH: {stats['with_positive_ath']}")
    print(f"   Max ATH: {stats['max_ath'] or 0}")
    print(f"   Avg ATH: {stats['avg_ath'] or 0:.6f}")
    
    # Test 4: Top 5 ATH
    print("\n4. Top 5 ATH:")
    top_ath = await conn.fetch("""
        SELECT token_address, ath_price_sol, ath_timestamp 
        FROM coin_streams 
        WHERE is_active = TRUE 
          AND ath_price_sol > 0
        ORDER BY ath_price_sol DESC 
        LIMIT 5
    """)
    if top_ath:
        for i, row in enumerate(top_ath, 1):
            addr = row['token_address'][:12] + "..."
            print(f"   {i}. {addr}: {row['ath_price_sol']} SOL @ {row['ath_timestamp']}")
    else:
        print("   ⚠️  Noch keine ATH-Werte vorhanden (normal beim Start)")
    
    # Test 5: Recent ATH Updates
    print("\n5. Recent ATH-Updates (letzte 10 Minuten):")
    recent = await conn.fetch("""
        SELECT 
            token_address,
            ath_price_sol,
            ath_timestamp,
            EXTRACT(EPOCH FROM (NOW() - ath_timestamp)) / 60 as minutes_ago
        FROM coin_streams 
        WHERE is_active = TRUE 
          AND ath_timestamp > NOW() - INTERVAL '10 minutes'
        ORDER BY ath_timestamp DESC
        LIMIT 5
    """)
    if recent:
        for row in recent:
            addr = row['token_address'][:12] + "..."
            print(f"   {addr}: {row['ath_price_sol']} SOL ({row['minutes_ago']:.1f} min ago)")
    else:
        print("   ⚠️  Keine Updates in den letzten 10 Minuten (normal wenn keine neuen ATHs)")
    
    # Test 6: Konsistenz-Check
    print("\n6. Konsistenz-Check (ATH vs. coin_metrics):")
    consistency = await conn.fetchrow("""
        SELECT 
            COUNT(*) as inconsistent_count
        FROM coin_streams cs
        JOIN coin_metrics cm ON cs.token_address = cm.mint
        WHERE cs.is_active = TRUE
          AND cs.ath_price_sol > 0
          AND cm.timestamp > NOW() - INTERVAL '1 hour'
          AND cm.price_close > cs.ath_price_sol * 1.01  -- ATH sollte >= aktueller Preis sein
        LIMIT 10
    """)
    if consistency['inconsistent_count'] == 0:
        print("   ✅ Keine Inkonsistenzen gefunden")
    else:
        print(f"   ⚠️  {consistency['inconsistent_count']} mögliche Inkonsistenzen gefunden")
    
    print("\n" + "=" * 60)
    print("TEST ABGESCHLOSSEN")
    print("=" * 60)
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(test_ath())

