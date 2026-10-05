"""Acceso a PostgreSQL: carga del catálogo y aplicación de lotes del outbox en UNA transacción."""
from datetime import datetime

import psycopg

from collector.models import TagInfo


def _ts(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


class Repository:
    # ── PASO 1 · Conexión con reapertura automática ──────────────────────────
    def __init__(self, dsn: str):
        self._dsn = dsn
        self._conn: psycopg.Connection | None = None

    def _connection(self) -> psycopg.Connection:
        if self._conn is None or self._conn.closed:
            # autocommit: las transacciones las controlamos explícitamente con conn.transaction()
            self._conn = psycopg.connect(self._dsn, connect_timeout=5, autocommit=True)
        return self._conn

    def close(self) -> None:
        if self._conn is not None and not self._conn.closed:
            self._conn.close()
        self._conn = None

    # ── PASO 2 · Datos de arranque ───────────────────────────────────────────
    def load_catalog(self) -> list[TagInfo]:
        with self._connection().cursor() as cur:
            cur.execute(
                "SELECT t.id, a.id, a.code, t.name, t.unit, t.opc_node "
                "FROM tags t JOIN assets a ON a.id = t.asset_id ORDER BY t.id"
            )
            return [TagInfo(*row) for row in cur.fetchall()]

    def load_open_states(self) -> dict[int, int]:
        """Estado actual de cada equipo (evento abierto), para no duplicar el primer cambio."""
        with self._connection().cursor() as cur:
            cur.execute("SELECT asset_id, state FROM machine_events WHERE end_ts IS NULL")
            return {asset_id: state for asset_id, state in cur.fetchall()}

    def load_open_alarms(self) -> set[tuple[int, str]]:
        with self._connection().cursor() as cur:
            cur.execute("SELECT asset_id, rule FROM alarms WHERE cleared_ts IS NULL")
            return {(asset_id, rule) for asset_id, rule in cur.fetchall()}

    # ── PASO 3 · Aplicar un lote (todo o nada) ───────────────────────────────
    def apply(self, records: list[dict]) -> None:
        """Si algo falla se hace rollback y se relanza: el outbox conserva el lote para reintentar."""
        conn = self._connection()
        try:
            with conn.transaction(), conn.cursor() as cur:
                pending_readings: list[tuple] = []
                for rec in records:
                    if rec["kind"] == "reading":
                        pending_readings.append((rec["tag_id"], _ts(rec["ts"]), rec["value"]))
                        continue
                    # Vaciamos las lecturas acumuladas antes de un evento para respetar el orden.
                    self._flush_readings(cur, pending_readings)
                    if rec["kind"] == "state_change":
                        self._apply_state_change(cur, rec)
                    elif rec["kind"] == "alarm":
                        self._apply_alarm(cur, rec)
                self._flush_readings(cur, pending_readings)
        except Exception:
            self.close()  # fuerza una conexión nueva en el siguiente intento
            raise

    @staticmethod
    def _flush_readings(cur, pending: list[tuple]) -> None:
        if pending:
            # ON CONFLICT: si un lote se reenvía tras un corte, no duplica lecturas.
            cur.executemany(
                "INSERT INTO readings (tag_id, ts, value) VALUES (%s, %s, %s) "
                "ON CONFLICT DO NOTHING", pending)
            pending.clear()

    @staticmethod
    def _apply_state_change(cur, rec: dict) -> None:
        cur.execute("SELECT id, state FROM machine_events WHERE asset_id = %s AND end_ts IS NULL",
                    (rec["asset_id"],))
        open_event = cur.fetchone()
        if open_event and open_event[1] == rec["state"]:
            return  # ya aplicado (reenvío): idempotente
        ts = _ts(rec["ts"])
        if open_event:
            cur.execute("UPDATE machine_events SET end_ts = %s WHERE id = %s", (ts, open_event[0]))
        cur.execute("INSERT INTO machine_events (asset_id, state, start_ts) VALUES (%s, %s, %s)",
                    (rec["asset_id"], rec["state"], ts))

    @staticmethod
    def _apply_alarm(cur, rec: dict) -> None:
        ts = _ts(rec["ts"])
        if rec["action"] == "raise":
            cur.execute(
                "INSERT INTO alarms (asset_id, rule, severity, message, value, raised_ts) "
                "VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (asset_id, rule) WHERE cleared_ts IS NULL DO NOTHING",
                (rec["asset_id"], rec["rule"], rec["severity"], rec["message"], rec["value"], ts))
        else:
            cur.execute(
                "UPDATE alarms SET cleared_ts = %s "
                "WHERE asset_id = %s AND rule = %s AND cleared_ts IS NULL",
                (ts, rec["asset_id"], rec["rule"]))
