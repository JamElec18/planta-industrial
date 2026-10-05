"""Sesión OPC UA: conexión, suscripción a cambios y vigilancia de la conexión."""
import asyncio
import logging
from typing import Callable

from asyncua import Client, ua

from collector.models import TagInfo
from collector.pipeline import Pipeline

log = logging.getLogger("collector.opc")

NAMESPACE_URI = "urn:planta:linea1"  # debe coincidir con el del simulador


# ── PASO 1 · Receptor de notificaciones ──────────────────────────────────────
class _Handler:
    """asyncua llama a este objeto cada vez que un nodo suscrito cambia de valor."""

    def __init__(self, pipeline: Pipeline):
        self._pipeline = pipeline

    def datachange_notification(self, node, val, data):
        try:
            self._pipeline.on_value(node.nodeid.Identifier, val)
        except Exception:  # un error en un valor no debe tumbar la suscripción
            log.exception("Error procesando %s", node.nodeid)

    def status_change_notification(self, status):
        log.warning("Cambio de estado de la suscripción: %s", status)


# ── PASO 2 · Una sesión completa ─────────────────────────────────────────────
async def run_session(endpoint: str, catalog: list[TagInfo], pipeline: Pipeline,
                      sampling_ms: int, on_connected: Callable[[], None]) -> None:
    """Corre hasta que la conexión falle (siempre termina lanzando una excepción)."""
    async with Client(url=endpoint, timeout=5) as client:
        idx = await client.get_namespace_index(NAMESPACE_URI)
        subscription = await client.create_subscription(sampling_ms, _Handler(pipeline))
        nodes = [client.get_node(ua.NodeId(tag.opc_node, idx)) for tag in catalog]
        await subscription.subscribe_data_change(nodes)
        log.info("Conectado a %s; suscrito a %d tags", endpoint, len(nodes))
        on_connected()

        # ── PASO 3 · Vigilante (watchdog) ────────────────────────────────────
        # Leer el estado del servidor cada 2 s: si el servidor cae, esta lectura falla y salimos.
        status_node = client.get_node(ua.NodeId(ua.ObjectIds.Server_ServerStatus_State))
        while True:
            await asyncio.sleep(2)
            await asyncio.wait_for(status_node.read_value(), timeout=5)
