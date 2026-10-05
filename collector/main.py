"""Collector: OPC UA -> outbox SQLite -> PostgreSQL, con reconexión automática en ambos extremos.

Ejecutar:  python -m collector.main
"""
import asyncio
import logging

from collector.alarms import AlarmEngine
from collector.buffer import Outbox
from collector.config import Settings
from collector.db import Repository
from collector.logging_setup import setup_logging
from collector.opcua_client import run_session
from collector.pipeline import Pipeline
from collector.resilience import Backoff

log = logging.getLogger("collector")


# ── PASO 1 · Arranque: esperar a PostgreSQL y cargar el catálogo ─────────────
async def load_startup_data(repo: Repository):
    """Reintenta hasta que la base responda; devuelve catálogo, estados y alarmas abiertas."""
    backoff = Backoff()
    while True:
        try:
            return await asyncio.to_thread(
                lambda: (repo.load_catalog(), repo.load_open_states(), repo.load_open_alarms())
            )
        except Exception as exc:
            delay = backoff.next()
            log.warning("PostgreSQL no disponible al arrancar (%s); reintento en %.1fs", exc, delay)
            await asyncio.sleep(delay)


# ── PASO 2 · Reenviador: outbox -> PostgreSQL ────────────────────────────────
async def forward_loop(outbox: Outbox, repo: Repository, batch_size: int, interval: float) -> None:
    """Envía lotes en orden y borra del outbox SOLO tras confirmar. Si falla, reintenta con backoff."""
    backoff = Backoff()
    while True:
        batch = outbox.peek(batch_size)
        if not batch:
            await asyncio.sleep(interval)
            continue
        try:
            await asyncio.to_thread(repo.apply, [record for _, record in batch])
            outbox.delete_upto(batch[-1][0])
            backoff.reset()
        except Exception as exc:
            delay = backoff.next()
            log.warning("No se pudo escribir en PostgreSQL (%s). Pendientes en buffer: %d. Reintento en %.1fs",
                        exc, outbox.count(), delay)
            await asyncio.sleep(delay)


# ── PASO 3 · Bucle OPC UA con reconexión ─────────────────────────────────────
async def opc_loop(cfg: Settings, catalog, pipeline: Pipeline) -> None:
    backoff = Backoff()
    while True:
        try:
            await run_session(cfg.opc_endpoint, catalog, pipeline, cfg.sampling_ms, backoff.reset)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            delay = backoff.next()
            log.warning("Sesión OPC UA perdida (%s: %s). Reconectando en %.1fs",
                        type(exc).__name__, exc, delay)
            await asyncio.sleep(delay)


# ── PASO 4 · Ensamble ────────────────────────────────────────────────────────
async def main() -> None:
    cfg = Settings.from_env()
    setup_logging(cfg.log_level)

    repo = Repository(cfg.pg_dsn)
    outbox = Outbox(cfg.outbox_path)
    catalog, open_states, open_alarms = await load_startup_data(repo)
    log.info("Catálogo cargado: %d tags. Pendientes en outbox: %d", len(catalog), outbox.count())

    pipeline = Pipeline(catalog, outbox, AlarmEngine(active=open_alarms), open_states)
    forwarder = asyncio.create_task(forward_loop(outbox, repo, cfg.forward_batch, cfg.forward_interval))
    try:
        await opc_loop(cfg, catalog, pipeline)
    finally:
        forwarder.cancel()
        repo.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
