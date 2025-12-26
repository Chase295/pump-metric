-- ============================================================================
-- PUMP METRIC - Alle Tabellen leeren (EINFACHE VERSION)
-- ============================================================================
-- ⚠️  WARNUNG: Diese Query löscht ALLE Daten aus allen Tabellen!
-- ⚠️  Verwende nur für Test-/Entwicklungs-Datenbanken!
-- ============================================================================
-- 
-- VERWENDUNG:
--   1. Kopiere die Queries unten
--   2. Führe sie in deinem PostgreSQL-Client aus (psql, pgAdmin, DBeaver, etc.)
-- ============================================================================

-- ============================================================================
-- OPTION 1: TRUNCATE (schnell, setzt Auto-Increment zurück)
-- ============================================================================

BEGIN;

-- Leere alle Tabellen (Reihenfolge ist wichtig wegen Foreign Keys)
TRUNCATE TABLE coin_metrics CASCADE;
TRUNCATE TABLE coin_streams CASCADE;
TRUNCATE TABLE discovered_coins CASCADE;

-- ref_coin_phases NICHT leeren (Referenz-Daten sollten erhalten bleiben)

COMMIT;

-- ============================================================================
-- OPTION 2: DELETE (wenn TRUNCATE nicht funktioniert)
-- ============================================================================
-- 
-- BEGIN;
-- 
-- DELETE FROM coin_metrics;
-- DELETE FROM coin_streams;
-- DELETE FROM discovered_coins;
-- -- DELETE FROM ref_coin_phases;  -- Referenz-Daten behalten
-- 
-- COMMIT;
-- 
-- ============================================================================

-- ============================================================================
-- OPTION 3: Nur coin_metrics leeren (Coins bleiben erhalten)
-- ============================================================================
-- 
-- TRUNCATE TABLE coin_metrics;
-- 
-- ============================================================================

-- ============================================================================
-- Prüfen ob Tabellen leer sind
-- ============================================================================
-- 
-- SELECT 
--     'coin_metrics' as tabelle, COUNT(*) as anzahl FROM coin_metrics
-- UNION ALL
-- SELECT 
--     'coin_streams', COUNT(*) FROM coin_streams
-- UNION ALL
-- SELECT 
--     'discovered_coins', COUNT(*) FROM discovered_coins;
-- 
-- ============================================================================

