"""Pipeline de procesamiento: valor OPC UA -> registros (lectura, cambio de estado, alarma) -> outbox."""
import logging
from datetime import datetime, timezone

from collector.alarms import AlarmEngine
from collector.buffer import Outbox
from collector.models import TagInfo

log = logging.getLogger("collector.pipeline")


class Pipeline:
    # ── PASO 1 · Construcción ────────────────────────────────────────────────
    def __init__(self, catalog: list[TagInfo], outbox: Outbox, alarm_engine: AlarmEngine,
                 initial_states: dict[int, int] | None = None):
        self._by_node = {tag.opc_node: tag for tag in catalog}
        self._outbox = outbox
        self._alarms = alarm_engine
        self._last_state = dict(initial_states or {})  # asset_id -> último estado conocido

    # ── PASO 2 · Entrada de un valor ─────────────────────────────────────────
    def on_value(self, node_identifier: str, value, ts: datetime | None = None) -> None:
        """Punto de entrada: lo llama la suscripción OPC UA en cada cambio de un nodo."""
        tag = self._by_node.get(node_identifier)
        if tag is None:
            return
        try:
            number = float(value)
        except (TypeError, ValueError):
            log.warning("Valor no numérico ignorado en %s: %r", node_identifier, value)
            return

        # La marca de tiempo es la de recepción, en UTC (siempre guardamos UTC).
        ts = ts or datetime.now(timezone.utc)
        iso = ts.isoformat()

        # ── PASO 3 · Lectura cruda ───────────────────────────────────────────
        records = [{"kind": "reading", "ts": iso, "tag_id": tag.tag_id, "value": number}]

        # ── PASO 4 · Cambio de estado (solo si el estado realmente cambió) ───
        if tag.name == "State":
            state = int(number)
            if self._last_state.get(tag.asset_id) != state:
                self._last_state[tag.asset_id] = state
                records.append({"kind": "state_change", "ts": iso,
                                "asset_id": tag.asset_id, "state": state})

        # ── PASO 5 · Alarmas ─────────────────────────────────────────────────
        for ev in self._alarms.evaluate(tag.asset_id, tag.name, number, ts):
            records.append({"kind": "alarm", "action": ev.action, "ts": iso,
                            "asset_id": ev.asset_id, "rule": ev.rule, "severity": ev.severity,
                            "message": ev.message, "value": ev.value})
            log.info("Alarma %s: %s en activo %s (valor=%s)", ev.action, ev.rule, tag.asset_code, number)

        # ── PASO 6 · Persistencia local inmediata (outbox) ───────────────────
        self._outbox.push_many(records)
