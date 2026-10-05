"""
API de Órdenes de Trabajo (ejemplo didáctico)
---------------------------------------------
Mini API REST para registrar órdenes de mantenimiento de equipos de planta.
Stack: FastAPI (framework web) + Pydantic (validación) + SQLite (base de datos SQL).

Ejecutar:   uvicorn main:app --reload
Documentos: http://127.0.0.1:8000/docs
"""

# =============================================================================
# PASO 1. IMPORTACIONES
# Librería estándar para BD y fechas; FastAPI para la API; Pydantic para validar.
# =============================================================================
import os
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field


# =============================================================================
# PASO 2. CONFIGURACIÓN
# Ruta del archivo de BD (se puede cambiar con la variable de entorno DB_PATH)
# y los valores válidos de estado de una orden.
# =============================================================================
DB_PATH = os.getenv("DB_PATH", "ordenes.db")

Estado = Literal["ABIERTA", "EN_PROCESO", "CERRADA"]


# =============================================================================
# PASO 3. CAPA DE BASE DE DATOS
# Una función abre/cierra la conexión de forma segura; otra crea la tabla.
# =============================================================================
@contextmanager
def conexion():
    """3.1 Abre la conexión, confirma cambios (commit) y siempre la cierra."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Permite leer columnas por nombre: fila["equipo"]
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """3.2 Crea la tabla 'ordenes' si todavía no existe."""
    with conexion() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ordenes (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                equipo         TEXT    NOT NULL,
                descripcion    TEXT    NOT NULL,
                prioridad      INTEGER NOT NULL,
                estado         TEXT    NOT NULL DEFAULT 'ABIERTA',
                fecha_creacion TEXT    NOT NULL
            )
            """
        )


def fila_a_dict(fila: sqlite3.Row) -> dict:
    """3.3 Convierte una fila de SQLite en diccionario (FastAPI lo vuelve JSON)."""
    return dict(fila)


# =============================================================================
# PASO 4. MODELOS (ESQUEMAS) CON PYDANTIC
# Definen la "forma" del JSON que entra y sale. Si el cliente manda datos
# inválidos, FastAPI responde 422 automáticamente sin tocar la BD.
# =============================================================================
class OrdenCrear(BaseModel):
    """4.1 Lo que el cliente envía para CREAR una orden (POST)."""
    equipo: str = Field(..., min_length=1, max_length=50, examples=["BOMBA-101"])
    descripcion: str = Field(..., min_length=3, max_length=200, examples=["Fuga en sello mecánico"])
    prioridad: int = Field(2, ge=1, le=3, description="1 = alta, 2 = media, 3 = baja")


class OrdenActualizar(BaseModel):
    """4.2 Lo que el cliente envía para MODIFICAR una orden (PATCH). Todo opcional."""
    equipo: Optional[str] = Field(None, min_length=1, max_length=50)
    descripcion: Optional[str] = Field(None, min_length=3, max_length=200)
    prioridad: Optional[int] = Field(None, ge=1, le=3)
    estado: Optional[Estado] = None


class Orden(BaseModel):
    """4.3 Lo que la API DEVUELVE al cliente (respuesta)."""
    id: int
    equipo: str
    descripcion: str
    prioridad: int
    estado: Estado
    fecha_creacion: str


# =============================================================================
# PASO 5. CREACIÓN DE LA APLICACIÓN
# 'lifespan' corre código al arrancar el servidor (aquí: preparar la BD).
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()   # 5.1 Al iniciar: asegurar que la tabla exista
    yield       # 5.2 Aquí la API atiende peticiones
    # 5.3 Al apagar: (nada que limpiar en este ejemplo)


app = FastAPI(
    title="API de Órdenes de Trabajo",
    description="Ejemplo didáctico de API REST para mantenimiento industrial.",
    version="1.0.0",
    lifespan=lifespan,
)


# =============================================================================
# PASO 6. ENDPOINTS (RUTAS)
# Cada función = una operación. El decorador indica MÉTODO HTTP + RUTA.
# =============================================================================

# 6.1 GET /  -> Verificación de salud ("¿la API está viva?")
@app.get("/", tags=["Sistema"])
def salud():
    return {"estado": "ok", "servicio": "api-ordenes"}


# 6.2 GET /ordenes  -> Listar órdenes (filtro opcional por estado)
#     Ejemplo: /ordenes?estado=ABIERTA
@app.get("/ordenes", response_model=list[Orden], tags=["Órdenes"])
def listar_ordenes(estado: Optional[Estado] = Query(None, description="Filtrar por estado")):
    with conexion() as conn:
        if estado:
            filas = conn.execute(
                "SELECT * FROM ordenes WHERE estado = ? ORDER BY id", (estado,)
            ).fetchall()
        else:
            filas = conn.execute("SELECT * FROM ordenes ORDER BY id").fetchall()
    return [fila_a_dict(f) for f in filas]


# 6.3 GET /ordenes/{orden_id}  -> Consultar UNA orden por su id
@app.get("/ordenes/{orden_id}", response_model=Orden, tags=["Órdenes"])
def obtener_orden(orden_id: int):
    with conexion() as conn:
        fila = conn.execute("SELECT * FROM ordenes WHERE id = ?", (orden_id,)).fetchone()
    if fila is None:
        raise HTTPException(status_code=404, detail=f"Orden {orden_id} no encontrada")
    return fila_a_dict(fila)


# 6.4 POST /ordenes  -> Crear una orden nueva (responde 201 Created)
@app.post("/ordenes", response_model=Orden, status_code=status.HTTP_201_CREATED, tags=["Órdenes"])
def crear_orden(datos: OrdenCrear):
    fecha = datetime.now().isoformat(timespec="seconds")
    with conexion() as conn:
        # Los '?' son parámetros: evitan inyección SQL (nunca concatenar texto del usuario)
        cursor = conn.execute(
            "INSERT INTO ordenes (equipo, descripcion, prioridad, fecha_creacion) VALUES (?, ?, ?, ?)",
            (datos.equipo, datos.descripcion, datos.prioridad, fecha),
        )
        nuevo_id = cursor.lastrowid
        fila = conn.execute("SELECT * FROM ordenes WHERE id = ?", (nuevo_id,)).fetchone()
    return fila_a_dict(fila)


# 6.5 PATCH /ordenes/{orden_id}  -> Modificar solo los campos enviados
@app.patch("/ordenes/{orden_id}", response_model=Orden, tags=["Órdenes"])
def actualizar_orden(orden_id: int, datos: OrdenActualizar):
    cambios = datos.model_dump(exclude_unset=True)  # Solo lo que el cliente mandó
    if not cambios:
        raise HTTPException(status_code=400, detail="No se enviaron campos para actualizar")

    # Los nombres de columna vienen del modelo Pydantic (no del usuario), por eso es seguro armarlos
    set_sql = ", ".join(f"{campo} = ?" for campo in cambios)
    valores = list(cambios.values()) + [orden_id]

    with conexion() as conn:
        cursor = conn.execute(f"UPDATE ordenes SET {set_sql} WHERE id = ?", valores)
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Orden {orden_id} no encontrada")
        fila = conn.execute("SELECT * FROM ordenes WHERE id = ?", (orden_id,)).fetchone()
    return fila_a_dict(fila)


# 6.6 DELETE /ordenes/{orden_id}  -> Eliminar una orden (responde 204 sin cuerpo)
@app.delete("/ordenes/{orden_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Órdenes"])
def eliminar_orden(orden_id: int):
    with conexion() as conn:
        cursor = conn.execute("DELETE FROM ordenes WHERE id = ?", (orden_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Orden {orden_id} no encontrada")
    return None
