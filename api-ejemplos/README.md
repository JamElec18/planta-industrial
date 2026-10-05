# Ejemplos de APIs (aprendizaje)

Ejercicios previos a la Fase 3 (órdenes de trabajo e inventario). Son independientes
del resto del proyecto: no usan Docker ni PostgreSQL.

| Carpeta | Qué muestra |
|---|---|
| `api-simple/` | API mínima en memoria (menú de restaurante): GET y POST con FastAPI. |
| `api-ordenes/` | API REST de órdenes de trabajo: CRUD completo, validación con Pydantic, SQLite, pruebas con pytest y un cliente con `requests`. |

## API de órdenes de trabajo

```bash
cd api-ejemplos/api-ordenes
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

uvicorn main:app --reload      # servidor en http://127.0.0.1:8000 (docs en /docs)
pytest -v                      # 9 pruebas automáticas
python cliente.py              # cliente que consume la API (con el servidor encendido)
```

| Método | Ruta | Acción |
|---|---|---|
| GET | `/ordenes` | Listar (filtro opcional `?estado=ABIERTA`) |
| GET | `/ordenes/{id}` | Consultar una orden |
| POST | `/ordenes` | Crear (201) |
| PATCH | `/ordenes/{id}` | Modificar campos (estado, prioridad…) |
| DELETE | `/ordenes/{id}` | Eliminar (204) |

## API simple

```bash
cd api-ejemplos/api-simple
pip install fastapi uvicorn
uvicorn api_simple:app --reload
```
