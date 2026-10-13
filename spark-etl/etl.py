"""ETL con PySpark para la Línea 1: CSV crudo -> datos limpios -> indicadores OEE por turno.

  Extraer:     lee el historial minuto a minuto (CSV) con un esquema explícito.
  Transformar: limpia, asigna turno y calcula Disponibilidad, Rendimiento, Calidad y OEE.
  Cargar:      guarda Parquet particionado por fecha y un resumen en CSV.

Ejecutar:  python etl.py [ruta_csv_entrada] [carpeta_salida]
"""
import sys

from pyspark.sql import Column, DataFrame, SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql.types import (DoubleType, IntegerType, StringType, StructField, StructType,
                               TimestampType)

# ── PASO 1 · Configuración ───────────────────────────────────────────────────
ENTRADA = "datos/crudo/historial_linea1.csv"
SALIDA = "datos/salida"

PIEZAS_IDEALES_POR_MINUTO = 60       # velocidad de diseño de cada equipo
TEMP_VALIDA = (0.0, 150.0)           # fuera de este rango la lectura es un error de sensor
TEMP_ALARMA = 80.0                   # a partir de aquí se considera temperatura alta
ESTADOS_VALIDOS = ["CORRIENDO", "PARO", "FALLA"]

# Esquema explícito: más rápido que inferirlo y evita sorpresas de tipos.
ESQUEMA = StructType([
    StructField("fecha_hora", TimestampType(), True),
    StructField("equipo", StringType(), True),
    StructField("estado", StringType(), True),
    StructField("piezas_buenas", IntegerType(), True),
    StructField("piezas_rechazadas", IntegerType(), True),
    StructField("temperatura", DoubleType(), True),
])


# ── PASO 2 · Sesión de Spark ─────────────────────────────────────────────────
def crear_spark(nombre: str = "etl-linea1") -> SparkSession:
    """Spark en modo local: usa todos los núcleos de la máquina como si fueran un clúster."""
    return (SparkSession.builder
            .appName(nombre)
            .master("local[*]")
            .config("spark.sql.session.timeZone", "UTC")    # horas tal cual vienen en el CSV
            .config("spark.sql.shuffle.partitions", "4")    # pocos datos: pocas particiones
            .config("spark.ui.enabled", "false")
            .getOrCreate())


# ── PASO 3 · Extraer: lectura del CSV crudo ──────────────────────────────────
def leer_crudo(spark: SparkSession, ruta: str) -> DataFrame:
    """Valores que no encajan con el esquema (texto vacío, etc.) se leen como nulos."""
    return (spark.read
            .option("header", True)
            .option("timestampFormat", "yyyy-MM-dd HH:mm:ss")
            .option("mode", "PERMISSIVE")
            .schema(ESQUEMA)
            .csv(ruta))


# ── PASO 4 · Transformar: limpieza ───────────────────────────────────────────
def limpiar(df: DataFrame) -> DataFrame:
    """Normaliza nombres, descarta renglones inservibles, anula lecturas imposibles y quita duplicados."""
    t_min, t_max = TEMP_VALIDA
    return (df
            # 4.1 · " llenadora " y "Llenadora" pasan a ser "LLENADORA"
            .withColumn("equipo", F.upper(F.trim("equipo")))
            .withColumn("estado", F.upper(F.trim("estado")))
            # 4.2 · Sin fecha, equipo o estado válido el renglón no sirve
            .dropna(subset=["fecha_hora", "equipo", "estado"])
            .filter(F.col("equipo") != "")
            .filter(F.col("estado").isin(ESTADOS_VALIDOS))
            # 4.3 · Temperatura imposible (-999) = error de sensor: se deja como nulo, no se inventa
            .withColumn("temperatura",
                        F.when(F.col("temperatura").between(t_min, t_max), F.col("temperatura")))
            # 4.4 · Contador sin dato = 0 piezas en ese minuto
            .fillna({"piezas_buenas": 0, "piezas_rechazadas": 0})
            # 4.5 · Un solo renglón por equipo y minuto (después de normalizar el nombre)
            .dropDuplicates(["fecha_hora", "equipo"]))


def reporte_calidad(crudo: DataFrame, limpio: DataFrame) -> dict:
    """Cuántos renglones entraron, cuántos sobrevivieron y cuántas lecturas se anularon."""
    t_min, t_max = TEMP_VALIDA
    leidos = crudo.count()
    validos = limpio.count()
    return {
        "renglones_leidos": leidos,
        "renglones_validos": validos,
        "renglones_descartados": leidos - validos,
        "temperaturas_fuera_de_rango": crudo.filter(~F.col("temperatura").between(t_min, t_max)).count(),
    }


# ── PASO 5 · Transformar: turnos ─────────────────────────────────────────────
def agregar_turno(df: DataFrame) -> DataFrame:
    """A = 06-14 h, B = 14-22 h, C = 22-06 h.

    Lo de 00:00 a 05:59 pertenece al turno C del DÍA ANTERIOR (así se reporta en planta).
    """
    hora = F.hour("fecha_hora")
    dia = F.to_date("fecha_hora")
    return (df
            .withColumn("turno", F.when((hora >= 6) & (hora < 14), "A")
                                  .when((hora >= 14) & (hora < 22), "B")
                                  .otherwise("C"))
            .withColumn("fecha", F.when(hora < 6, F.date_sub(dia, 1)).otherwise(dia)))


# ── PASO 6 · Transformar: indicadores OEE ────────────────────────────────────
def _dividir(numerador: Column, denominador: Column) -> Column:
    """División segura: si el denominador es 0 devuelve 0 en vez de lanzar un error."""
    return F.coalesce(F.try_divide(numerador, denominador), F.lit(0.0))


def calcular_kpis(df: DataFrame, claves: list[str]) -> DataFrame:
    """Agrupa por `claves` (turno, equipo, día...) y calcula el OEE de cada grupo.

    Disponibilidad = minutos corriendo / minutos registrados
    Rendimiento    = piezas producidas / piezas que se debieron producir a velocidad ideal
    Calidad        = piezas buenas / piezas producidas
    OEE            = Disponibilidad x Rendimiento x Calidad
    """
    def contar_si(condicion: Column) -> Column:
        return F.sum(F.when(condicion, 1).otherwise(0))

    # 6.1 · Sumas por grupo
    agrupado = df.groupBy(*claves).agg(
        F.count("*").alias("minutos_registrados"),
        contar_si(F.col("estado") == "CORRIENDO").alias("minutos_corriendo"),
        contar_si(F.col("estado") == "FALLA").alias("minutos_falla"),
        F.sum("piezas_buenas").alias("piezas_buenas"),
        F.sum("piezas_rechazadas").alias("piezas_rechazadas"),
        F.round(F.avg("temperatura"), 1).alias("temp_promedio"),
        contar_si(F.col("temperatura") >= TEMP_ALARMA).alias("minutos_temp_alta"),
    )

    # 6.2 · Indicadores a partir de las sumas
    producidas = F.col("piezas_buenas") + F.col("piezas_rechazadas")
    return (agrupado
            .withColumn("disponibilidad",
                        F.round(_dividir(F.col("minutos_corriendo"), F.col("minutos_registrados")), 4))
            .withColumn("rendimiento",
                        F.round(_dividir(producidas, F.col("minutos_corriendo") * PIEZAS_IDEALES_POR_MINUTO), 4))
            .withColumn("calidad",
                        F.round(_dividir(F.col("piezas_buenas"), producidas), 4))
            .withColumn("oee",
                        F.round(F.col("disponibilidad") * F.col("rendimiento") * F.col("calidad"), 4)))


# ── PASO 7 · Transformar: ranking diario con una función de ventana ──────────
def ranking_diario(kpis_turno: DataFrame) -> DataFrame:
    """Dentro de cada día, ordena las combinaciones equipo-turno de mejor (1) a peor OEE."""
    ventana = Window.partitionBy("fecha").orderBy(F.desc("oee"))
    return kpis_turno.withColumn("posicion_en_el_dia", F.dense_rank().over(ventana))


# ── PASO 8 · Cargar: escritura de resultados ─────────────────────────────────
def guardar(limpio: DataFrame, kpis_turno: DataFrame, resumen: DataFrame, salida: str) -> None:
    # Parquet: formato columnar comprimido, el estándar en data lakes. Particionar por fecha
    # permite leer solo los días que se necesitan.
    limpio.write.mode("overwrite").partitionBy("fecha").parquet(f"{salida}/historial_limpio")
    kpis_turno.write.mode("overwrite").partitionBy("fecha").parquet(f"{salida}/kpis_turno")
    # CSV de un solo archivo para abrir en Excel o Power BI.
    resumen.coalesce(1).write.mode("overwrite").option("header", True).csv(f"{salida}/resumen_equipos")


# ── PASO 9 · Orquestación ────────────────────────────────────────────────────
def main(entrada: str = ENTRADA, salida: str = SALIDA) -> None:
    spark = crear_spark()
    spark.sparkContext.setLogLevel("WARN")

    # 9.1 · Extraer y limpiar
    crudo = leer_crudo(spark, entrada)
    limpio = agregar_turno(limpiar(crudo)).cache()   # se reutiliza varias veces: se guarda en memoria
    print("\n== Calidad de datos ==")
    for clave, valor in reporte_calidad(crudo, limpio).items():
        print(f"  {clave:<30}{valor:>10,}")

    # 9.2 · Indicadores a tres niveles de detalle
    kpis_turno = ranking_diario(calcular_kpis(limpio, ["fecha", "turno", "equipo"]))
    resumen_equipos = calcular_kpis(limpio, ["equipo"]).orderBy("oee")
    resumen_turnos = calcular_kpis(limpio, ["turno"]).orderBy("turno")

    print("== OEE de la semana por equipo (de peor a mejor) ==")
    resumen_equipos.select("equipo", "disponibilidad", "rendimiento", "calidad", "oee",
                           "minutos_falla", "minutos_temp_alta").show(truncate=False)

    print("== OEE de la semana por turno ==")
    resumen_turnos.select("turno", "disponibilidad", "rendimiento", "calidad", "oee").show()

    # 9.3 · La misma información consultada con Spark SQL
    kpis_turno.createOrReplaceTempView("kpis_turno")
    print("== Top 5 turnos con más minutos en falla (Spark SQL) ==")
    spark.sql("""
        SELECT fecha, turno, equipo, minutos_falla, ROUND(oee * 100, 1) AS oee_pct
        FROM kpis_turno
        ORDER BY minutos_falla DESC, fecha
        LIMIT 5
    """).show()

    # 9.4 · Guardar
    guardar(limpio, kpis_turno, resumen_equipos, salida)
    print(f"Resultados guardados en {salida}/")
    spark.stop()


if __name__ == "__main__":
    main(*sys.argv[1:3])
