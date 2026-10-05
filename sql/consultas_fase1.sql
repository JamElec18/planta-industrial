-- =============================================================================
-- Consultas de la Fase 1 · Planta Industrial Línea 1
-- Para revisar qué hay en la base de datos y qué está pasando en la línea.
--
-- Cómo usarlo (desde la carpeta del proyecto, con los contenedores arriba):
--   · Todas de golpe:
--       docker compose exec -T db psql -U planta -d planta < sql/consultas_fase1.sql
--   · Una por una (modo interactivo, copia y pega cada consulta):
--       docker compose exec db psql -U planta -d planta
--       (para salir escribe  \q)
-- =============================================================================

-- ── PASO 0 · Zona horaria ────────────────────────────────────────────────────
-- En la base todo se guarda en UTC; esto solo cambia cómo se MUESTRAN las horas.
SET TIME ZONE 'America/Mexico_City';


-- ── PASO 1 · Inventario: qué tablas hay y cuántos renglones tiene cada una ───
-- La primera foto de la base: si "readings" crece cada vez que la corres, el sistema está vivo.
SELECT 'assets'         AS tabla, COUNT(*) AS renglones FROM assets
UNION ALL SELECT 'tags',           COUNT(*) FROM tags
UNION ALL SELECT 'machine_states', COUNT(*) FROM machine_states
UNION ALL SELECT 'readings',       COUNT(*) FROM readings
UNION ALL SELECT 'machine_events', COUNT(*) FROM machine_events
UNION ALL SELECT 'alarms',         COUNT(*) FROM alarms;


-- ── PASO 2 · Catálogo: equipos y los datos (tags) que se miden de cada uno ───
-- 3 equipos × 5 tags = 15 renglones. opc_node es el "nombre" del dato en el simulador.
SELECT a.code AS equipo, t.id AS tag_id, t.name AS tag, t.unit AS unidad, t.opc_node
FROM tags t
JOIN assets a ON a.id = t.asset_id
ORDER BY a.id, t.id;


-- ── PASO 3 · ¿Está llegando información? ─────────────────────────────────────
-- Última lectura recibida y hace cuántos segundos llegó. Si pasan de ~10 s, algo está detenido.
SELECT MAX(ts)                                           AS ultima_lectura,
       ROUND(EXTRACT(EPOCH FROM now() - MAX(ts)))        AS hace_segundos,
       MIN(ts)                                           AS primera_lectura,
       COUNT(*)                                          AS total_lecturas
FROM readings;


-- ── PASO 4 · Tablero "en vivo": valor actual de cada tag ─────────────────────
-- DISTINCT ON se queda con la lectura más reciente de cada tag.
SELECT DISTINCT ON (t.id)
       a.code AS equipo, t.name AS tag, r.value AS valor, t.unit AS unidad, r.ts AS hora
FROM readings r
JOIN tags t   ON t.id = r.tag_id
JOIN assets a ON a.id = t.asset_id
ORDER BY t.id, r.ts DESC;


-- ── PASO 5 · Estado actual de cada máquina y desde cuándo ────────────────────
-- El evento con end_ts NULL es el estado en el que está ahora mismo.
SELECT a.code AS equipo, s.name AS estado_actual, e.start_ts AS desde,
       date_trunc('second', now() - e.start_ts) AS lleva
FROM machine_events e
JOIN assets a         ON a.id = e.asset_id
JOIN machine_states s ON s.state = e.state
WHERE e.end_ts IS NULL
ORDER BY a.id;


-- ── PASO 6 · Historial de estados (los últimos 15 cambios) ───────────────────
-- Cada renglón es un periodo: "la Tapadora estuvo en FALLA de tal hora a tal hora".
SELECT a.code AS equipo, s.name AS estado, e.start_ts AS inicio, e.end_ts AS fin,
       date_trunc('second', COALESCE(e.end_ts, now()) - e.start_ts) AS duracion
FROM machine_events e
JOIN assets a         ON a.id = e.asset_id
JOIN machine_states s ON s.state = e.state
ORDER BY e.start_ts DESC
LIMIT 15;


-- ── PASO 7 · Tiempo en cada estado por máquina (última hora) ─────────────────
-- Recorta cada periodo a la ventana de 1 h y suma. El % CORRIENDO es la base de la
-- "Disponibilidad" que usarás en el OEE de la Fase 2.
WITH ventana AS (
    SELECT now() - interval '1 hour' AS desde, now() AS hasta
),
recortado AS (
    SELECT e.asset_id, e.state,
           GREATEST(e.start_ts, v.desde)                 AS ini,
           LEAST(COALESCE(e.end_ts, v.hasta), v.hasta)   AS fin
    FROM machine_events e, ventana v
    WHERE e.start_ts < v.hasta
      AND COALESCE(e.end_ts, v.hasta) > v.desde
)
SELECT a.code AS equipo, s.name AS estado,
       date_trunc('second', SUM(fin - ini)) AS tiempo,
       ROUND(100.0 * EXTRACT(EPOCH FROM SUM(fin - ini))
             / SUM(EXTRACT(EPOCH FROM SUM(fin - ini))) OVER (PARTITION BY a.id), 1) AS porcentaje
FROM recortado r
JOIN assets a         ON a.id = r.asset_id
JOIN machine_states s ON s.state = r.state
GROUP BY a.id, a.code, s.state, s.name
ORDER BY a.id, s.state;


-- ── PASO 8 · Cuántas veces paró o falló cada máquina ─────────────────────────
-- Un número alto de fallas señala al equipo que más atención de mantenimiento necesita.
SELECT a.code AS equipo,
       COUNT(*) FILTER (WHERE e.state = 1) AS arranques,
       COUNT(*) FILTER (WHERE e.state = 0) AS paros,
       COUNT(*) FILTER (WHERE e.state = 2) AS fallas
FROM machine_events e
JOIN assets a ON a.id = e.asset_id
GROUP BY a.id, a.code
ORDER BY a.id;


-- ── PASO 9 · Producción: piezas buenas, rechazadas y % de calidad ────────────
-- Los contadores son acumulados y vuelven a 0 si el equipo se reinicia.
-- Por eso se calcula la diferencia entre lecturas (LAG): si sale negativa fue un
-- reinicio y se toma el valor nuevo completo.
WITH deltas AS (
    SELECT t.asset_id, t.name,
           r.value - LAG(r.value) OVER (PARTITION BY r.tag_id ORDER BY r.ts) AS delta,
           r.value
    FROM readings r
    JOIN tags t ON t.id = r.tag_id
    WHERE t.name IN ('GoodCount', 'RejectCount')
),
piezas AS (
    SELECT asset_id, name,
           SUM(CASE WHEN delta < 0 THEN value ELSE delta END)::numeric AS total
    FROM deltas
    WHERE delta IS NOT NULL
    GROUP BY asset_id, name
)
SELECT a.code AS equipo,
       COALESCE(MAX(total) FILTER (WHERE p.name = 'GoodCount'), 0)   AS buenas,
       COALESCE(MAX(total) FILTER (WHERE p.name = 'RejectCount'), 0) AS rechazadas,
       ROUND(100.0 * COALESCE(MAX(total) FILTER (WHERE p.name = 'GoodCount'), 0)
             / NULLIF(SUM(total), 0), 2) AS calidad_pct
FROM piezas p
JOIN assets a ON a.id = p.asset_id
GROUP BY a.id, a.code
ORDER BY a.id;


-- ── PASO 10 · Temperatura y presión: mínimo, promedio y máximo ───────────────
-- Resumen estadístico por equipo; sirve para ver si algún equipo trabaja más caliente.
SELECT a.code AS equipo, t.name AS tag, t.unit AS unidad,
       ROUND(MIN(r.value)::numeric, 2) AS minimo,
       ROUND(AVG(r.value)::numeric, 2) AS promedio,
       ROUND(MAX(r.value)::numeric, 2) AS maximo
FROM readings r
JOIN tags t   ON t.id = r.tag_id
JOIN assets a ON a.id = t.asset_id
WHERE t.name IN ('Temperature', 'Pressure')
GROUP BY a.id, a.code, t.name, t.unit
ORDER BY a.id, t.name;


-- ── PASO 11 · Tendencia de temperatura minuto a minuto (últimos 15 min) ──────
-- date_trunc agrupa las lecturas por minuto: es la tabla que alimentaría una gráfica.
SELECT date_trunc('minute', r.ts) AS minuto, a.code AS equipo,
       ROUND(AVG(r.value)::numeric, 1) AS temp_promedio,
       ROUND(MAX(r.value)::numeric, 1) AS temp_maxima
FROM readings r
JOIN tags t   ON t.id = r.tag_id
JOIN assets a ON a.id = t.asset_id
WHERE t.name = 'Temperature'
  AND r.ts >= now() - interval '15 minutes'
GROUP BY 1, a.id, a.code
ORDER BY 1 DESC, a.id;


-- ── PASO 12 · Alarmas activas en este momento ────────────────────────────────
-- cleared_ts NULL = la alarma sigue encendida.
SELECT a.code AS equipo, al.rule AS regla, al.severity AS severidad, al.message AS mensaje,
       al.value AS valor_al_disparar, al.raised_ts AS desde,
       date_trunc('second', now() - al.raised_ts) AS lleva
FROM alarms al
JOIN assets a ON a.id = al.asset_id
WHERE al.cleared_ts IS NULL
ORDER BY al.raised_ts;


-- ── PASO 13 · Historial de alarmas (las últimas 15) con su duración ──────────
SELECT a.code AS equipo, al.rule AS regla, al.severity AS severidad,
       ROUND(al.value::numeric, 1) AS valor, al.raised_ts AS se_activo, al.cleared_ts AS se_limpio,
       date_trunc('second', COALESCE(al.cleared_ts, now()) - al.raised_ts) AS duracion
FROM alarms al
JOIN assets a ON a.id = al.asset_id
ORDER BY al.raised_ts DESC
LIMIT 15;


-- ── PASO 14 · Resumen de alarmas por equipo y regla ──────────────────────────
-- Cuántas veces sonó cada alarma y cuánto duró en promedio: base para priorizar mantenimiento.
SELECT a.code AS equipo, al.rule AS regla,
       COUNT(*)                                                      AS veces,
       date_trunc('second', AVG(al.cleared_ts - al.raised_ts))       AS duracion_promedio,
       date_trunc('second', MAX(al.cleared_ts - al.raised_ts))       AS duracion_maxima
FROM alarms al
JOIN assets a ON a.id = al.asset_id
GROUP BY a.id, a.code, al.rule
ORDER BY a.id, al.rule;


-- ── PASO 15 · Detección de huecos: lecturas por minuto (últimos 30 min) ──────
-- generate_series crea todos los minutos aunque no haya datos: un minuto en 0 es un
-- hueco real. Úsala después de la prueba "docker compose stop db / start db" para
-- demostrar que el outbox no perdió nada.
SELECT m.minuto, COUNT(r.ts) AS lecturas
FROM generate_series(date_trunc('minute', now() - interval '30 minutes'),
                     date_trunc('minute', now()),
                     interval '1 minute') AS m(minuto)
LEFT JOIN readings r
       ON r.ts >= m.minuto AND r.ts < m.minuto + interval '1 minute'
GROUP BY m.minuto
ORDER BY m.minuto DESC;


-- ── PASO 16 · Tamaño que ocupa cada tabla en disco ───────────────────────────
-- "readings" es la que más crece; útil para el pendiente de retención/particionado.
SELECT relname AS tabla,
       pg_size_pretty(pg_total_relation_size(relid)) AS tamano_total
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
