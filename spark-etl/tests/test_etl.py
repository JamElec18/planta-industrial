"""Pruebas de las transformaciones del ETL con DataFrames pequeños hechos a mano."""
import pytest
from pyspark.sql import functions as F

from etl import agregar_turno, calcular_kpis, crear_spark, limpiar

COLUMNAS = ("fecha_hora string, equipo string, estado string, "
            "piezas_buenas int, piezas_rechazadas int, temperatura double")


# ── PASO 1 · Preparación ─────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def spark():
    """Una sola sesión de Spark para todas las pruebas (arrancarla tarda unos segundos)."""
    sesion = crear_spark("pruebas-etl")
    yield sesion
    sesion.stop()


def crear_df(spark, filas):
    """Las fechas se escriben como texto y Spark las convierte con su propia zona horaria (UTC),
    así las pruebas dan lo mismo en la Mac que dentro de Docker."""
    return spark.createDataFrame(filas, COLUMNAS).withColumn("fecha_hora", F.to_timestamp("fecha_hora"))


# ── PASO 2 · Limpieza ────────────────────────────────────────────────────────
def test_limpiar_normaliza_quita_duplicados_y_renglones_invalidos(spark):
    df = crear_df(spark, [
        ("2026-10-05 08:00:00", "LLENADORA",   "CORRIENDO", 50, 1, 55.0),
        ("2026-10-05 08:00:00", " llenadora ", "corriendo", 50, 1, 55.0),   # duplicado mal escrito
        ("2026-10-05 08:01:00", "TAPADORA",    "CORRIENDO", None, 2, -999.0),  # sensor y contador malos
        ("2026-10-05 08:02:00", None,          "PARO",      0, 0, 30.0),    # sin equipo
        ("2026-10-05 08:03:00", "TAPADORA",    "N/A",       0, 0, 30.0),    # estado desconocido
    ])
    filas = {r["equipo"]: r for r in limpiar(df).collect()}

    assert sorted(filas) == ["LLENADORA", "TAPADORA"]
    assert filas["TAPADORA"]["temperatura"] is None      # -999 se anula
    assert filas["TAPADORA"]["piezas_buenas"] == 0       # contador vacío = 0


# ── PASO 3 · Turnos ──────────────────────────────────────────────────────────
def test_turnos_y_madrugada_pertenece_al_dia_anterior(spark):
    df = crear_df(spark, [
        ("2026-10-06 05:59:00", "LLENADORA", "PARO", 0, 0, 30.0),
        ("2026-10-06 06:00:00", "LLENADORA", "PARO", 0, 0, 30.0),
        ("2026-10-06 14:00:00", "LLENADORA", "PARO", 0, 0, 30.0),
        ("2026-10-06 22:00:00", "LLENADORA", "PARO", 0, 0, 30.0),
    ])
    resultado = [(str(r["fecha"]), r["turno"])
                 for r in agregar_turno(df).orderBy("fecha_hora").collect()]

    assert resultado == [
        ("2026-10-05", "C"),   # 05:59 todavía es el turno nocturno del día 5
        ("2026-10-06", "A"),
        ("2026-10-06", "B"),
        ("2026-10-06", "C"),
    ]


# ── PASO 4 · Indicadores OEE ─────────────────────────────────────────────────
def test_calculo_de_oee(spark):
    # 4 minutos: 3 corriendo (150 piezas, 10 rechazadas) y 1 en paro.
    df = crear_df(spark, [
        ("2026-10-05 08:00:00", "LLENADORA", "CORRIENDO", 60, 0, 55.0),
        ("2026-10-05 08:01:00", "LLENADORA", "CORRIENDO", 50, 10, 56.0),
        ("2026-10-05 08:02:00", "LLENADORA", "CORRIENDO", 30, 0, 85.0),
        ("2026-10-05 08:03:00", "LLENADORA", "PARO", 0, 0, 40.0),
    ])
    k = calcular_kpis(df, ["equipo"]).collect()[0]

    assert k["disponibilidad"] == pytest.approx(3 / 4, abs=1e-4)
    assert k["rendimiento"] == pytest.approx(150 / 180, abs=1e-4)   # 3 min x 60 pzas ideales
    assert k["calidad"] == pytest.approx(140 / 150, abs=1e-4)
    assert k["oee"] == pytest.approx(0.75 * (150 / 180) * (140 / 150), abs=1e-3)
    assert k["minutos_temp_alta"] == 1


def test_equipo_que_no_corrio_da_oee_cero_sin_error(spark):
    df = crear_df(spark, [("2026-10-05 08:00:00", "TAPADORA", "FALLA", 0, 0, 30.0)])
    k = calcular_kpis(df, ["equipo"]).collect()[0]

    assert (k["disponibilidad"], k["rendimiento"], k["calidad"], k["oee"]) == (0, 0, 0, 0)
    assert k["minutos_falla"] == 1
