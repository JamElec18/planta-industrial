# ETL con PySpark · Indicadores OEE de la Línea 1

Pipeline **batch** que toma una semana de historial "sucio" de la línea de envasado (minuto a minuto,
3 equipos) y lo convierte en datos limpios e **indicadores OEE por equipo y por turno**.

```
generar_datos.py                    etl.py (PySpark)
─────────────────    ┌─────────────────────────────────────────────────────┐
CSV crudo  ────────► │ Extraer → Limpiar → Turnos → KPIs OEE → Ranking      │ ──► Parquet (por fecha)
~30 mil renglones    │ esquema   nulos,     A/B/C    groupBy    ventana      │ ──► CSV resumen
con errores          │ explícito duplicados                    + Spark SQL  │
                     └─────────────────────────────────────────────────────┘
```

## Qué demuestra

| Técnica de Spark | Dónde |
|---|---|
| Lectura de CSV con **esquema explícito** | `leer_crudo` |
| **Limpieza de datos**: normalizar texto, nulos, valores imposibles, duplicados | `limpiar` |
| Columnas derivadas con `when` / fechas (`hour`, `to_date`, `date_sub`) | `agregar_turno` |
| **Agregaciones** con `groupBy().agg()` reutilizables en varios niveles | `calcular_kpis` |
| **Funciones de ventana** (`Window`, `dense_rank`) | `ranking_diario` |
| **Spark SQL** sobre una vista temporal | `main` |
| `cache()` para no recalcular un DataFrame reutilizado | `main` |
| Escritura en **Parquet particionado** y CSV | `guardar` |
| **Pruebas unitarias** de transformaciones con pytest | `tests/test_etl.py` |

## Indicadores

| Indicador | Fórmula |
|---|---|
| Disponibilidad | minutos corriendo / minutos registrados |
| Rendimiento | piezas producidas / (minutos corriendo × 60 piezas ideales) |
| Calidad | piezas buenas / piezas producidas |
| **OEE** | Disponibilidad × Rendimiento × Calidad |

Turnos: **A** 06-14 h, **B** 14-22 h, **C** 22-06 h (la madrugada cuenta para el día anterior).

## Ejecutar (con Docker, sin instalar Java ni Spark)

```bash
cd spark-etl
docker build -t spark-etl .                              # la primera vez tarda unos minutos

docker run --rm -v "$PWD/datos:/app/datos" spark-etl      # genera los datos y corre el ETL
docker run --rm spark-etl pytest -v                      # 4 pruebas automáticas
```

Los resultados quedan en tu Mac, en `spark-etl/datos/salida/`:

| Carpeta | Contenido |
|---|---|
| `historial_limpio/` | Los ~30 mil renglones ya limpios, en Parquet, una subcarpeta por día |
| `kpis_turno/` | OEE de cada equipo en cada turno de cada día, con su posición en el día |
| `resumen_equipos/` | Un CSV con el OEE semanal de cada equipo (se abre en Excel) |

## Resultado esperado

La semilla fija hace que los datos sean siempre los mismos, así que deberías ver aproximadamente:

- 30,565 renglones leídos, 30,199 válidos y 366 descartados (duplicados y renglones inservibles).
- **TAPADORA** es el peor equipo (OEE ≈ 67.5 %): es el que más falla.
- El **turno C** (nocturno) es el peor turno (OEE ≈ 66 %): su rendimiento baja a ≈ 82 %.

## Para el currículum

> Desarrollé un pipeline ETL en **PySpark** que procesa el historial minuto a minuto de una línea
> de producción: limpieza de datos (duplicados, nulos y lecturas de sensor inválidas), cálculo de
> **OEE** por equipo y turno con agregaciones, funciones de ventana y Spark SQL, y almacenamiento en
> **Parquet** particionado. Incluye pruebas unitarias con pytest y ejecución en Docker.
