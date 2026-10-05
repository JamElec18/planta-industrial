"""Utilidades de resiliencia."""
import random


# ── PASO 1 · Reintentos con espera exponencial ───────────────────────────────
class Backoff:
    """Espera 1s, 2s, 4s... hasta un tope, con jitter para no reintentar todos al mismo tiempo."""

    def __init__(self, base: float = 1.0, cap: float = 30.0):
        self.base = base
        self.cap = cap
        self._attempt = 0

    def next(self) -> float:
        delay = min(self.cap, self.base * (2 ** min(self._attempt, 10)))
        self._attempt += 1
        return delay * random.uniform(0.5, 1.0)

    def reset(self) -> None:
        self._attempt = 0
