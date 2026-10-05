"""Configuración del collector, leída de variables de entorno (con valores para desarrollo local)."""
import os
from dataclasses import dataclass


# ── PASO 1 · Parámetros ──────────────────────────────────────────────────────
@dataclass(frozen=True)
class Settings:
    opc_endpoint: str = "opc.tcp://localhost:4840/planta"
    pg_dsn: str = "postgresql://planta:planta@localhost:5432/planta"
    outbox_path: str = "./data/outbox.db"
    sampling_ms: int = 500          # cada cuánto el servidor revisa cambios en los nodos
    forward_batch: int = 500        # registros por lote hacia PostgreSQL
    forward_interval: float = 1.0   # espera cuando no hay nada pendiente
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        d = cls()
        return cls(
            opc_endpoint=os.getenv("OPC_ENDPOINT", d.opc_endpoint),
            pg_dsn=os.getenv("PG_DSN", d.pg_dsn),
            outbox_path=os.getenv("OUTBOX_PATH", d.outbox_path),
            sampling_ms=int(os.getenv("SAMPLING_MS", d.sampling_ms)),
            forward_batch=int(os.getenv("FORWARD_BATCH", d.forward_batch)),
            forward_interval=float(os.getenv("FORWARD_INTERVAL", d.forward_interval)),
            log_level=os.getenv("LOG_LEVEL", d.log_level),
        )
