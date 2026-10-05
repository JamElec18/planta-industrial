"""Logging estructurado en JSON: una línea por evento, fácil de filtrar y de enviar a un agregador."""
import json
import logging


# ── PASO 1 · Formateador JSON ────────────────────────────────────────────────
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


# ── PASO 2 · Activación ──────────────────────────────────────────────────────
def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    logging.getLogger("asyncua").setLevel(logging.WARNING)  # muy ruidoso en INFO
