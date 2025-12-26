-- ============================================================================
-- PUMP METRIC - Alle Tabellen leeren
-- ============================================================================
-- ⚠️  WARNUNG: Diese Query löscht ALLE Daten aus allen Tabellen!
-- ⚠️  Verwende nur für Test-/Entwicklungs-Datenbanken!
-- ============================================================================
-- 
-- Verwendung:
--   psql -d crypto -f sql/truncate_all_tables.sql
-- 
-- Oder in psql:
--   \i sql/truncate_all_tables.sql
-- ============================================================================

-- Methode 1: TRUNCATE (schneller, setzt Auto-Increment zurück)
-- Reihenfolge ist wichtig wegen Foreign Key Constraints

BEGIN;

-- 1. Leere coin_metrics (hat keine Foreign Keys)
TRUNCATE TABLE coin_metrics CASCADE;

-- 2. Leere coin_streams (kann Foreign Keys zu discovered_coins haben)
TRUNCATE TABLE coin_streams CASCADE;

-- 3. Leere discovered_coins (Referenz-Tabelle)
TRUNCATE TABLE discovered_coins CASCADE;

-- 4. Leere ref_coin_phases (Referenz-Tabelle, sollte normalerweise nicht geleert werden)
-- TRUNCATE TABLE ref_coin_phases CASCADE;  -- AUSKOMMENTIERT: Referenz-Daten sollten erhalten bleiben

COMMIT;

-- ============================================================================
-- ALTERNATIVE: DELETE (wenn TRUNCATE nicht funktioniert)
-- ============================================================================
-- 
-- Falls TRUNCATE aus irgendeinem Grund nicht funktioniert, verwende DELETE:
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
-- ALTERNATIVE: Alle Tabellen automatisch finden und leeren
-- ============================================================================
-- 
-- Diese Query findet alle Tabellen im 'public' Schema und leert sie:
-- 
-- DO $$
-- DECLARE
--     r RECORD;
-- BEGIN
--     FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') 
--     LOOP
--         EXECUTE 'TRUNCATE TABLE ' || quote_ident(r.tablename) || ' CASCADE';
--         RAISE NOTICE 'Gelöscht: %', r.tablename;
--     END LOOP;
-- END $$;
-- 
-- ============================================================================

-- ============================================================================
-- NUR coin_metrics leeren (wenn nur Metriken gelöscht werden sollen)
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

