"""Genera un CSV "sucio" con una semana de historial de la Línea 1, minuto a minuto.

Simula lo que exportaría un historiador de planta real: datos con duplicados, nombres de
equipo mal escritos, sensores con error y renglones incompletos. El ETL (etl.py) los limpia.

Ejecutar:  python generar_datos.py
Salida:    datos/crudo/historial_linea1.csv  (~31 mil renglones)
"""
import csv
import os
import random
from datetime import datetime, timedelta

# ── PASO 1 · Parámetros de la simulación ─────────────────────────────────────
# Una semana exacta de turnos: del lunes 06:00 al lunes siguiente 05:59 (21 turnos por equipo).
INICIO = datetime(2026, 10, 5, 6, 0)
MINUTOS = 7 * 24 * 60
SALIDA = "datos/crudo/historial_linea1.csv"
SEMILLA = 42  # misma semilla = mismos datos en cada ejecución (resultados reproducibles)

# Cada equipo tiene su "personalidad": probabilidad de falla por minuto y % de rechazo.
EQUIPOS = {
    "LLENADORA":    {"p_falla": 0.006, "p_rechazo": 0.02},
    "TAPADORA":     {"p_falla": 0.015, "p_rechazo": 0.04},   # el equipo problemático
    "ETIQUETADORA": {"p_falla": 0.009, "p_rechazo": 0.03},
}
PIEZAS_IDEALES_POR_MINUTO = 60


# ── PASO 2 · Comportamiento de un equipo minuto a minuto ─────────────────────
def simular_equipo(nombre: str, params: dict) -> list[list]:
    """Máquina de estados (PARO / CORRIENDO / FALLA) + producción + temperatura."""
    filas = []
    estado = "PARO"
    sobrecalentamiento = 0  # minutos restantes de un episodio de temperatura alta
    for m in range(MINUTOS):
        ts = INICIO + timedelta(minutes=m)
        r = random.random()

        # Transiciones de estado
        if estado == "PARO" and r < 0.30:
            estado = "CORRIENDO"
        elif estado == "CORRIENDO":
            if r < params["p_falla"]:
                estado = "FALLA"
            elif r < params["p_falla"] + 0.03:
                estado = "PARO"
        elif estado == "FALLA" and r < 0.15:
            estado = "PARO"

        # Producción: el turno nocturno (22:00-06:00) trabaja más lento.
        buenas = rechazadas = 0
        if estado == "CORRIENDO":
            nocturno = ts.hour >= 22 or ts.hour < 6
            minimo = 0.65 if nocturno else 0.80
            piezas = random.randint(int(PIEZAS_IDEALES_POR_MINUTO * minimo), PIEZAS_IDEALES_POR_MINUTO)
            rechazadas = sum(random.random() < params["p_rechazo"] for _ in range(piezas))
            buenas = piezas - rechazadas

        # Temperatura: ~55 °C corriendo, ~30 °C parado y episodios ocasionales de ~85 °C.
        if estado != "CORRIENDO":
            sobrecalentamiento = 0  # al detenerse el equipo se enfría
        elif sobrecalentamiento == 0 and random.random() < 0.004:
            sobrecalentamiento = random.randint(10, 25)
        if sobrecalentamiento > 0:
            temperatura = random.gauss(85, 2)
            sobrecalentamiento -= 1
        elif estado == "CORRIENDO":
            temperatura = random.gauss(55, 2)
        else:
            temperatura = random.gauss(30, 1.5)

        filas.append([ts.strftime("%Y-%m-%d %H:%M:%S"), nombre, estado,
                      buenas, rechazadas, round(temperatura, 2)])
    return filas


# ── PASO 3 · Ensuciar los datos (lo que pasa en la vida real) ────────────────
def ensuciar(filas: list[list]) -> list[list]:
    """Mete errores típicos de una exportación real para que el ETL tenga trabajo."""
    sucias = []
    for fila in filas:
        fila = list(fila)
        r = random.random()
        if r < 0.03:      # nombre de equipo con mayúsculas/espacios distintos
            fila[1] = random.choice([fila[1].lower(), f" {fila[1]} ", fila[1].title()])
        if random.random() < 0.003:   # sensor sin lectura
            fila[5] = ""
        if random.random() < 0.001:   # sensor con error (valor imposible)
            fila[5] = -999.0
        if random.random() < 0.001:   # contador sin dato
            fila[3] = ""
        if random.random() < 0.0005:  # renglón sin fecha: inservible
            fila[0] = ""
        if random.random() < 0.0005:  # estado desconocido
            fila[2] = "N/A"
        sucias.append(fila)
        if random.random() < 0.01:    # renglón duplicado (reenvío del historiador)
            sucias.append(list(fila))
    random.shuffle(sucias)  # las exportaciones no siempre vienen ordenadas
    return sucias


# ── PASO 4 · Escritura del CSV ───────────────────────────────────────────────
def main() -> None:
    random.seed(SEMILLA)
    filas = []
    for nombre, params in EQUIPOS.items():
        filas.extend(simular_equipo(nombre, params))
    filas = ensuciar(filas)

    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    with open(SALIDA, "w", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        escritor.writerow(["fecha_hora", "equipo", "estado", "piezas_buenas",
                           "piezas_rechazadas", "temperatura"])
        escritor.writerows(filas)
    print(f"Generados {len(filas):,} renglones en {SALIDA}")


if __name__ == "__main__":
    main()
