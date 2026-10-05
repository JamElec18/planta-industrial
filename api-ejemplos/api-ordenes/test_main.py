"""
Pruebas automatizadas de la API de Órdenes de Trabajo
-----------------------------------------------------
Ejecutar:  pytest -v
TestClient simula peticiones HTTP sin levantar el servidor real.
"""

# =============================================================================
# PASO 1. IMPORTACIONES
# =============================================================================
import pytest
from fastapi.testclient import TestClient

import main


# =============================================================================
# PASO 2. FIXTURE: CLIENTE CON BASE DE DATOS TEMPORAL
# Cada prueba usa una BD nueva y vacía en una carpeta temporal,
# así las pruebas no ensucian 'ordenes.db' ni dependen unas de otras.
# =============================================================================
@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", str(tmp_path / "test.db"))  # 2.1 BD temporal
    with TestClient(main.app) as c:                                    # 2.2 Arranca la app (crea tabla)
        yield c                                                        # 2.3 Entrega el cliente a la prueba


def crear(client, equipo="BOMBA-101", descripcion="Fuga en sello", prioridad=1):
    """2.4 Atajo para crear una orden dentro de las pruebas."""
    return client.post(
        "/ordenes",
        json={"equipo": equipo, "descripcion": descripcion, "prioridad": prioridad},
    )


# =============================================================================
# PASO 3. PRUEBAS DEL SISTEMA
# =============================================================================
def test_salud(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["estado"] == "ok"


# =============================================================================
# PASO 4. PRUEBAS DE CREACIÓN Y VALIDACIÓN
# =============================================================================
def test_crear_orden(client):
    r = crear(client)
    assert r.status_code == 201
    datos = r.json()
    assert datos["id"] == 1
    assert datos["equipo"] == "BOMBA-101"
    assert datos["estado"] == "ABIERTA"   # Estado por defecto


def test_crear_orden_invalida_devuelve_422(client):
    r = client.post("/ordenes", json={"equipo": "BOMBA-101", "descripcion": "x", "prioridad": 9})
    assert r.status_code == 422           # Descripción muy corta y prioridad fuera de rango


# =============================================================================
# PASO 5. PRUEBAS DE CONSULTA
# =============================================================================
def test_obtener_orden_existente(client):
    crear(client)
    r = client.get("/ordenes/1")
    assert r.status_code == 200
    assert r.json()["id"] == 1


def test_obtener_orden_inexistente_devuelve_404(client):
    r = client.get("/ordenes/999")
    assert r.status_code == 404


def test_listar_y_filtrar_por_estado(client):
    crear(client, equipo="BOMBA-101")
    crear(client, equipo="MOTOR-202")
    client.patch("/ordenes/2", json={"estado": "CERRADA"})

    assert len(client.get("/ordenes").json()) == 2
    abiertas = client.get("/ordenes", params={"estado": "ABIERTA"}).json()
    assert len(abiertas) == 1
    assert abiertas[0]["equipo"] == "BOMBA-101"


# =============================================================================
# PASO 6. PRUEBAS DE ACTUALIZACIÓN Y ELIMINACIÓN
# =============================================================================
def test_actualizar_orden(client):
    crear(client)
    r = client.patch("/ordenes/1", json={"estado": "EN_PROCESO", "prioridad": 2})
    assert r.status_code == 200
    assert r.json()["estado"] == "EN_PROCESO"
    assert r.json()["prioridad"] == 2
    assert r.json()["equipo"] == "BOMBA-101"  # Lo no enviado no cambia


def test_actualizar_sin_campos_devuelve_400(client):
    crear(client)
    r = client.patch("/ordenes/1", json={})
    assert r.status_code == 400


def test_eliminar_orden(client):
    crear(client)
    assert client.delete("/ordenes/1").status_code == 204
    assert client.get("/ordenes/1").status_code == 404
    assert client.delete("/ordenes/1").status_code == 404
