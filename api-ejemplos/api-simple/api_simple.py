"""
Mi primera API: El menú de un restaurante
-----------------------------------------
Instalar:  pip install fastapi uvicorn
Ejecutar:  uvicorn api_simple:app --reload
Probar:    abrir http://127.0.0.1:8000/docs en el navegador
"""

# =============================================================================
# PASO 1. IMPORTAR LA HERRAMIENTA
# FastAPI es la librería que convierte funciones de Python en una API.
# =============================================================================
from fastapi import FastAPI


# =============================================================================
# PASO 2. CREAR LA API (el "mesero")
# Este objeto recibe los pedidos y entrega las respuestas.
# =============================================================================
app = FastAPI(title="Menú del Restaurante")


# =============================================================================
# PASO 3. LOS DATOS (la "cocina")
# Una lista simple en memoria. Se borra al apagar el servidor.
# =============================================================================
menu = [
    {"id": 1, "platillo": "Tacos", "precio": 50},
    {"id": 2, "platillo": "Enchiladas", "precio": 80},
    {"id": 3, "platillo": "Pozole", "precio": 95},
]


# =============================================================================
# PASO 4. LAS RUTAS (lo que el cliente puede pedir)
# Cada función responde a una dirección (URL) y un método (GET, POST).
# =============================================================================

# 4.1 Saludo: comprobar que la API funciona
@app.get("/")
def inicio():
    return {"mensaje": "¡Bienvenido! Visita /menu para ver los platillos"}


# 4.2 Ver todo el menú
@app.get("/menu")
def ver_menu():
    return menu


# 4.3 Ver un solo platillo por su número
@app.get("/menu/{id}")
def ver_platillo(id: int):
    for platillo in menu:
        if platillo["id"] == id:
            return platillo
    return {"error": "Ese platillo no existe"}


# 4.4 Agregar un platillo nuevo
@app.post("/menu")
def agregar_platillo(platillo: str, precio: int):
    nuevo = {"id": len(menu) + 1, "platillo": platillo, "precio": precio}
    menu.append(nuevo)
    return nuevo
