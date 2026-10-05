"""Pruebas del pipeline: qué registros se generan a partir de los valores de OPC UA."""
from collector.alarms import AlarmEngine
from collector.buffer import Outbox
from collector.models import TagInfo
from collector.pipeline import Pipeline

CATALOG = [
    TagInfo(1, 10, "LLENADORA", "State", "estado", "Llenadora.State"),
    TagInfo(2, 10, "LLENADORA", "Temperature", "C", "Llenadora.Temperature"),
]


def build(initial_states=None):
    outbox = Outbox(":memory:")
    return Pipeline(CATALOG, outbox, AlarmEngine(), initial_states), outbox


def kinds(outbox):
    return [rec["kind"] for _, rec in outbox.peek(100)]


# ── PASO 1 · Cambio de estado ────────────────────────────────────────────────
def test_cambio_de_estado_se_registra_una_sola_vez():
    pipeline, outbox = build()
    pipeline.on_value("Llenadora.State", 1)
    pipeline.on_value("Llenadora.State", 1)   # mismo estado: solo lectura
    assert kinds(outbox) == ["reading", "state_change", "reading"]


def test_no_duplica_el_estado_ya_conocido_al_arrancar():
    pipeline, outbox = build(initial_states={10: 1})
    pipeline.on_value("Llenadora.State", 1)
    assert kinds(outbox) == ["reading"]


# ── PASO 2 · Alarmas ─────────────────────────────────────────────────────────
def test_temperatura_alta_genera_alarma():
    pipeline, outbox = build()
    pipeline.on_value("Llenadora.Temperature", 85.0)
    records = [rec for _, rec in outbox.peek(100)]
    assert [r["kind"] for r in records] == ["reading", "alarm"]
    assert records[1]["action"] == "raise" and records[1]["rule"] == "TEMP_ALTA"


def test_falla_de_equipo_genera_estado_y_alarma():
    pipeline, outbox = build()
    pipeline.on_value("Llenadora.State", 2)
    assert kinds(outbox) == ["reading", "state_change", "alarm"]


# ── PASO 3 · Entradas inválidas ──────────────────────────────────────────────
def test_ignora_nodos_desconocidos_y_valores_no_numericos():
    pipeline, outbox = build()
    pipeline.on_value("Otro.Nodo", 5)
    pipeline.on_value("Llenadora.Temperature", "abc")
    assert outbox.count() == 0
