"""Pruebas del motor de alarmas: histéresis, no duplicar, independencia entre equipos."""
from datetime import datetime, timezone

from collector.alarms import AlarmEngine

TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def actions(events):
    return [e.action for e in events]


# ── PASO 1 · Histéresis de temperatura ───────────────────────────────────────
def test_temp_alta_usa_histeresis():
    engine = AlarmEngine()
    assert engine.evaluate(1, "Temperature", 70, TS) == []
    assert actions(engine.evaluate(1, "Temperature", 81, TS)) == ["raise"]
    assert engine.evaluate(1, "Temperature", 78, TS) == []   # banda muerta 75-80: sigue activa
    assert engine.evaluate(1, "Temperature", 85, TS) == []   # no se duplica
    assert actions(engine.evaluate(1, "Temperature", 74, TS)) == ["clear"]


# ── PASO 2 · Falla de equipo por estado ──────────────────────────────────────
def test_falla_equipo_se_levanta_y_se_limpia():
    engine = AlarmEngine()
    assert actions(engine.evaluate(1, "State", 2, TS)) == ["raise"]
    assert actions(engine.evaluate(1, "State", 0, TS)) == ["clear"]


# ── PASO 3 · Independencia entre equipos ─────────────────────────────────────
def test_alarmas_de_equipos_distintos_son_independientes():
    engine = AlarmEngine()
    assert actions(engine.evaluate(1, "Temperature", 90, TS)) == ["raise"]
    assert actions(engine.evaluate(2, "Temperature", 90, TS)) == ["raise"]
    assert actions(engine.evaluate(1, "Temperature", 60, TS)) == ["clear"]
    assert engine.evaluate(2, "Temperature", 88, TS) == []


# ── PASO 4 · Reinicio del collector ──────────────────────────────────────────
def test_alarma_abierta_antes_del_reinicio_puede_limpiarse():
    engine = AlarmEngine(active={(1, "TEMP_ALTA")})
    assert engine.evaluate(1, "Temperature", 90, TS) == []   # ya estaba abierta
    assert actions(engine.evaluate(1, "Temperature", 60, TS)) == ["clear"]
