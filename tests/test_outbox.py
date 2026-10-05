"""Pruebas del outbox SQLite: orden, persistencia tras reinicio y borrado confirmado."""
from collector.buffer import Outbox


def test_conserva_orden_y_borra_solo_lo_confirmado(tmp_path):
    outbox = Outbox(str(tmp_path / "outbox.db"))
    outbox.push_many([{"n": 1}, {"n": 2}, {"n": 3}])

    batch = outbox.peek(2)
    assert [rec["n"] for _, rec in batch] == [1, 2]
    assert outbox.count() == 3              # peek no borra

    outbox.delete_upto(batch[-1][0])        # confirmamos solo los 2 primeros
    assert [rec["n"] for _, rec in outbox.peek(10)] == [3]


def test_los_datos_sobreviven_a_un_reinicio(tmp_path):
    path = str(tmp_path / "outbox.db")
    Outbox(path).push_many([{"n": 1}])
    assert [rec["n"] for _, rec in Outbox(path).peek(10)] == [1]
