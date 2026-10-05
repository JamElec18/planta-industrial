-- =============================================================================
-- Esquema base de la planta simulada (Línea 1)
-- Se ejecuta solo la primera vez que arranca el contenedor de PostgreSQL.
-- Para reiniciarlo desde cero:  docker compose down -v
-- =============================================================================

-- ── PASO 1 · Catálogo de activos y tags ──────────────────────────────────────
-- Activo = equipo físico. Tag = variable medida de ese equipo.
CREATE TABLE assets (
    id    SERIAL PRIMARY KEY,
    code  TEXT NOT NULL UNIQUE,
    name  TEXT NOT NULL,
    line  TEXT NOT NULL
);

CREATE TABLE tags (
    id        SERIAL PRIMARY KEY,
    asset_id  INT  NOT NULL REFERENCES assets(id),
    name      TEXT NOT NULL,
    unit      TEXT,
    opc_node  TEXT NOT NULL UNIQUE,      -- identificador del nodo en el servidor OPC UA
    UNIQUE (asset_id, name)
);

-- ── PASO 2 · Lecturas de proceso ─────────────────────────────────────────────
-- Serie de tiempo cruda. La PK (tag_id, ts) hace idempotente el reenvío desde el buffer.
CREATE TABLE readings (
    tag_id  INT              NOT NULL REFERENCES tags(id),
    ts      TIMESTAMPTZ      NOT NULL,
    value   DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (tag_id, ts)
);
CREATE INDEX ix_readings_ts ON readings (ts);

-- ── PASO 3 · Estados de máquina ──────────────────────────────────────────────
-- Un renglón por periodo en un estado; end_ts NULL = estado actual.
CREATE TABLE machine_states (
    state  SMALLINT PRIMARY KEY,
    name   TEXT NOT NULL
);
INSERT INTO machine_states VALUES (0, 'PARO'), (1, 'CORRIENDO'), (2, 'FALLA');

CREATE TABLE machine_events (
    id           BIGSERIAL PRIMARY KEY,
    asset_id     INT         NOT NULL REFERENCES assets(id),
    state        SMALLINT    NOT NULL REFERENCES machine_states(state),
    start_ts     TIMESTAMPTZ NOT NULL,
    end_ts       TIMESTAMPTZ,
    reason_code  TEXT                      -- se llenará desde el módulo de tablero/CMMS
);
CREATE INDEX ix_events_asset_start ON machine_events (asset_id, start_ts);
-- Garantiza un solo evento abierto por equipo (protege contra reenvíos duplicados).
CREATE UNIQUE INDEX ux_open_event ON machine_events (asset_id) WHERE end_ts IS NULL;

-- ── PASO 4 · Alarmas ─────────────────────────────────────────────────────────
CREATE TABLE alarms (
    id               BIGSERIAL PRIMARY KEY,
    asset_id         INT              NOT NULL REFERENCES assets(id),
    rule             TEXT             NOT NULL,
    severity         TEXT             NOT NULL,
    message          TEXT             NOT NULL,
    value            DOUBLE PRECISION,
    raised_ts        TIMESTAMPTZ      NOT NULL,
    cleared_ts       TIMESTAMPTZ,
    acknowledged_by  TEXT,
    acknowledged_ts  TIMESTAMPTZ
);
CREATE INDEX ix_alarms_raised ON alarms (raised_ts);
-- Una sola alarma abierta por (equipo, regla).
CREATE UNIQUE INDEX ux_open_alarm ON alarms (asset_id, rule) WHERE cleared_ts IS NULL;

-- ── PASO 5 · Datos semilla: línea de envasado ────────────────────────────────
INSERT INTO assets (code, name, line) VALUES
    ('LLENADORA',    'Llenadora',    'LINEA_1'),
    ('TAPADORA',     'Tapadora',     'LINEA_1'),
    ('ETIQUETADORA', 'Etiquetadora', 'LINEA_1');

-- Cada equipo tiene los mismos 5 tags; opc_node = "<Equipo>.<Tag>" (igual que en el simulador).
INSERT INTO tags (asset_id, name, unit, opc_node)
SELECT a.id, t.name, t.unit, a.name || '.' || t.name
FROM assets a
CROSS JOIN (VALUES
    ('State',       'estado'),
    ('GoodCount',   'pzas'),
    ('RejectCount', 'pzas'),
    ('Temperature', 'C'),
    ('Pressure',    'bar')
) AS t(name, unit);
