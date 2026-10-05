"""Modelos de datos compartidos por el collector (sin dependencias externas)."""
from dataclasses import dataclass

PARO, CORRIENDO, FALLA = 0, 1, 2


# ── PASO 1 · Descriptor de un tag ────────────────────────────────────────────
@dataclass(frozen=True)
class TagInfo:
    """Un tag del catálogo: une el nodo OPC UA con su tag y su equipo en la base de datos."""

    tag_id: int
    asset_id: int
    asset_code: str
    name: str
    unit: str | None
    opc_node: str
