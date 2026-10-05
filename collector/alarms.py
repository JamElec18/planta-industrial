"""Motor de alarmas por umbral con histéresis. Lógica pura: sin red ni base de datos."""
from dataclasses import dataclass
from datetime import datetime
from typing import Callable


# ── PASO 1 · Definición de reglas ────────────────────────────────────────────
@dataclass(frozen=True)
class AlarmRule:
    name: str
    tag: str
    severity: str
    message: str
    is_raised: Callable[[float], bool]   # condición para levantar la alarma
    is_cleared: Callable[[float], bool]  # condición (distinta) para limpiarla


# La zona entre 75 y 80 °C es "banda muerta": evita alarmas que titilan si la temperatura oscila.
DEFAULT_RULES = [
    AlarmRule("TEMP_ALTA", "Temperature", "alta", "Temperatura alta",
              lambda v: v >= 80.0, lambda v: v <= 75.0),
    AlarmRule("FALLA_EQUIPO", "State", "critica", "Equipo en falla",
              lambda v: v == 2, lambda v: v != 2),
]


# ── PASO 2 · Eventos que produce el motor ────────────────────────────────────
@dataclass(frozen=True)
class AlarmEvent:
    action: str  # "raise" | "clear"
    asset_id: int
    rule: str
    severity: str
    message: str
    value: float
    ts: datetime


# ── PASO 3 · Motor con memoria de alarmas activas ────────────────────────────
class AlarmEngine:
    def __init__(self, rules: list[AlarmRule] | None = None, active: set[tuple[int, str]] | None = None):
        self._rules_by_tag: dict[str, list[AlarmRule]] = {}
        for rule in rules or DEFAULT_RULES:
            self._rules_by_tag.setdefault(rule.tag, []).append(rule)
        # (asset_id, regla) abiertas; al reiniciar se cargan desde la base para poder cerrarlas.
        self._active = set(active or set())

    def evaluate(self, asset_id: int, tag: str, value: float, ts: datetime) -> list[AlarmEvent]:
        """Devuelve solo las transiciones (levantar/limpiar); nunca repite una alarma ya activa."""
        events = []
        for rule in self._rules_by_tag.get(tag, []):
            key = (asset_id, rule.name)
            if key in self._active:
                if rule.is_cleared(value):
                    self._active.discard(key)
                    events.append(AlarmEvent("clear", asset_id, rule.name, rule.severity,
                                             rule.message, value, ts))
            elif rule.is_raised(value):
                self._active.add(key)
                events.append(AlarmEvent("raise", asset_id, rule.name, rule.severity,
                                         rule.message, value, ts))
        return events
