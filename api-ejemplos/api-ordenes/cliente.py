"""
Cliente de la API de Órdenes de Trabajo
---------------------------------------
Este programa NO es la API: es otro programa que la USA, igual que Postman,
pero escrito en Python con la librería 'requests'.

Requisitos:  pip install requests
Uso:         1) En una terminal:  uvicorn main:app --reload
             2) En otra terminal: python cliente.py
"""

# =============================================================================
# PASO 1. IMPORTACIONES
# 'requests' es la librería estándar de facto para hacer peticiones HTTP.
# =============================================================================
import requests


# =============================================================================
# PASO 2. CONFIGURACIÓN
# Dirección base de la API y tiempo máximo de espera por petición.
# =============================================================================
BASE_URL = "http://127.0.0.1:8000"
TIMEOUT = 5  # segundos; sin timeout, el programa podría quedarse colgado para siempre


# =============================================================================
# PASO 3. FUNCIONES QUE HABLAN CON LA API
# Cada función equivale a una petición que antes hacías a mano en Postman.
# =============================================================================

def verificar_salud():
    """3.1 GET /  -> ¿La API está encendida?"""
    r = requests.get(f"{BASE_URL}/", timeout=TIMEOUT)
    r.raise_for_status()          # Si el código es 4xx o 5xx, lanza un error
    return r.json()               # Convierte el JSON de la respuesta en dict de Python


def crear_orden(equipo, descripcion, prioridad=2):
    """3.2 POST /ordenes  -> 'json=' envía el diccionario como Body JSON."""
    datos = {"equipo": equipo, "descripcion": descripcion, "prioridad": prioridad}
    r = requests.post(f"{BASE_URL}/ordenes", json=datos, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def listar_ordenes(estado=None):
    """3.3 GET /ordenes?estado=...  -> 'params=' arma la parte '?clave=valor' de la URL."""
    params = {"estado": estado} if estado else None
    r = requests.get(f"{BASE_URL}/ordenes", params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def obtener_orden(orden_id):
    """3.4 GET /ordenes/{id}  -> Devuelve la orden, o None si no existe (404)."""
    r = requests.get(f"{BASE_URL}/ordenes/{orden_id}", timeout=TIMEOUT)
    if r.status_code == 404:      # Revisar el código manualmente para decidir qué hacer
        return None
    r.raise_for_status()
    return r.json()


def cambiar_estado(orden_id, nuevo_estado):
    """3.5 PATCH /ordenes/{id}  -> Modifica solo el estado."""
    r = requests.patch(
        f"{BASE_URL}/ordenes/{orden_id}", json={"estado": nuevo_estado}, timeout=TIMEOUT
    )
    r.raise_for_status()
    return r.json()


def eliminar_orden(orden_id):
    """3.6 DELETE /ordenes/{id}  -> True si se borró (204)."""
    r = requests.delete(f"{BASE_URL}/ordenes/{orden_id}", timeout=TIMEOUT)
    return r.status_code == 204


# =============================================================================
# PASO 4. UTILIDAD PARA MOSTRAR RESULTADOS
# =============================================================================
def mostrar(titulo, ordenes):
    """4.1 Imprime una lista de órdenes como tabla sencilla."""
    print(f"\n--- {titulo} ({len(ordenes)}) ---")
    for o in ordenes:
        print(f"  #{o['id']:<3} {o['equipo']:<12} P{o['prioridad']}  {o['estado']:<11} {o['descripcion']}")


# =============================================================================
# PASO 5. FLUJO PRINCIPAL (el "guion" de la demostración)
# =============================================================================
def main():
    # 5.1 Confirmar que la API responde antes de hacer cualquier cosa
    print("Salud de la API:", verificar_salud())

    # 5.2 Crear varias órdenes de golpe con un ciclo (imposible de hacer tan rápido en Postman)
    pendientes = [
        ("BOMBA-101", "Fuga en sello mecánico", 1),
        ("MOTOR-202", "Vibración alta en rodamiento", 2),
        ("BANDA-303", "Ajuste de tensión", 3),
    ]
    creadas = [crear_orden(eq, desc, prio) for eq, desc, prio in pendientes]
    print(f"\nSe crearon {len(creadas)} órdenes: ids {[o['id'] for o in creadas]}")

    # 5.3 Listar todas
    mostrar("Todas las órdenes", listar_ordenes())

    # 5.4 Atender la primera orden creada y filtrar por estado
    primera = creadas[0]["id"]
    cambiar_estado(primera, "EN_PROCESO")
    mostrar("Órdenes ABIERTAS", listar_ordenes("ABIERTA"))
    mostrar("Órdenes EN_PROCESO", listar_ordenes("EN_PROCESO"))

    # 5.5 Manejar un error de validación (422) sin que el programa se caiga
    try:
        crear_orden("BOMBA-101", "x", prioridad=9)
    except requests.HTTPError as e:
        print(f"\nError esperado al crear orden inválida: {e.response.status_code}")
        for detalle in e.response.json()["detail"]:
            print(f"  - campo {detalle['loc'][-1]}: {detalle['msg']}")

    # 5.6 Consultar una orden que no existe (404)
    print("\nOrden 9999:", obtener_orden(9999))

    # 5.7 Eliminar la última orden creada y confirmar
    ultima = creadas[-1]["id"]
    print(f"\n¿Se eliminó la orden {ultima}?", eliminar_orden(ultima))
    print(f"¿Existe todavía la orden {ultima}?", obtener_orden(ultima) is not None)


# =============================================================================
# PASO 6. PUNTO DE ENTRADA
# Si el servidor está apagado, se muestra un mensaje claro en vez de un error largo.
# =============================================================================
if __name__ == "__main__":
    try:
        main()
    except requests.ConnectionError:
        print("No se pudo conectar. ¿Está corriendo 'uvicorn main:app --reload'?")
    except requests.Timeout:
        print(f"La API tardó más de {TIMEOUT} segundos en responder.")
