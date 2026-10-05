"""Outbox local en SQLite: patrón store-and-forward.

Todo registro se guarda primero en disco y solo se borra cuando PostgreSQL confirmó el guardado.
Así no se pierden datos si cae la base de datos, la red o el propio collector.
"""
import json
import os
import sqlite3
import threading


class Outbox:
    # ── PASO 1 · Apertura ────────────────────────────────────────────────────
    def __init__(self, path: str):
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()  # se usa desde el event loop y desde hilos
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=NORMAL")
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS outbox ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL)"
            )
            self._db.commit()

    # ── PASO 2 · Escritura ───────────────────────────────────────────────────
    def push_many(self, records: list[dict]) -> None:
        """Encola registros en orden; el id autoincremental preserva ese orden."""
        with self._lock, self._db:  # `with self._db` hace commit al salir
            self._db.executemany(
                "INSERT INTO outbox (payload) VALUES (?)", [(json.dumps(r),) for r in records]
            )

    # ── PASO 3 · Lectura y confirmación ──────────────────────────────────────
    def peek(self, limit: int) -> list[tuple[int, dict]]:
        """Devuelve los registros más antiguos sin borrarlos."""
        with self._lock:
            rows = self._db.execute(
                "SELECT id, payload FROM outbox ORDER BY id LIMIT ?", (limit,)
            ).fetchall()
        return [(row_id, json.loads(payload)) for row_id, payload in rows]

    def delete_upto(self, last_id: int) -> None:
        """Borra hasta `last_id` inclusive: se llama solo tras confirmar el guardado en PostgreSQL."""
        with self._lock, self._db:
            self._db.execute("DELETE FROM outbox WHERE id <= ?", (last_id,))

    def count(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
