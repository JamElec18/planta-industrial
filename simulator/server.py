"""Simulador OPC UA de una línea de envasado: Llenadora -> Tapadora -> Etiquetadora.

Hace de "PLC": publica estado, contadores, temperatura y presión de cada equipo.
"""
import asyncio
import logging
import os
import random

from asyncua import Server, ua

# ── PASO 1 · Configuración ───────────────────────────────────────────────────
# El namespace debe coincidir con el que busca el collector.
NAMESPACE_URI = "urn:planta:linea1"
ENDPOINT = os.getenv("SIM_ENDPOINT", "opc.tcp://0.0.0.0:4840/planta")
TICK_SECONDS = 1.0

PARO, CORRIENDO, FALLA = 0, 1, 2
MACHINE_NAMES = ["Llenadora", "Tapadora", "Etiquetadora"]

# (nombre del tag, valor inicial, tipo OPC UA). Enteros como Int64 y decimales como Double
# para que coincidan con el tipo que Python infiere al escribir.
TAGS = [
    ("State", 0, ua.VariantType.Int64),
    ("GoodCount", 0, ua.VariantType.Int64),
    ("RejectCount", 0, ua.VariantType.Int64),
    ("Temperature", 0.0, ua.VariantType.Double),
    ("Pressure", 0.0, ua.VariantType.Double),
]

log = logging.getLogger("simulator")


# ── PASO 2 · Comportamiento de un equipo ─────────────────────────────────────
class SimulatedMachine:
    """Máquina de estados + producción + variables de proceso, con aleatoriedad verosímil."""

    AMBIENT_TEMP = 28.0
    REJECT_PROBABILITY = 0.03

    def __init__(self, name: str):
        self.name = name
        self.state = PARO
        self.good = 0
        self.reject = 0
        self.temperature = self.AMBIENT_TEMP
        self.pressure = 0.0
        self._piece_accumulator = 0.0
        self._overheat_ticks = 0

    def step(self) -> None:
        """Avanza un segundo de simulación."""
        self._update_state()
        self._update_production()
        self._update_process_variables()

    def _update_state(self) -> None:
        # Transiciones probabilísticas por segundo: corre ~1 min, se para o falla, y arranca de nuevo.
        r = random.random()
        if self.state == PARO and r < 0.10:
            self.state = CORRIENDO
        elif self.state == CORRIENDO:
            if r < 0.005:
                self.state = FALLA
            elif r < 0.015:
                self.state = PARO
        elif self.state == FALLA and r < 0.04:
            self.state = PARO  # reparada; vuelve a paro y luego arranca

    def _update_production(self) -> None:
        # Velocidad ideal = 1 pieza/s; la real varía entre 70% y 100% (pérdida de rendimiento).
        if self.state != CORRIENDO:
            return
        self._piece_accumulator += random.uniform(0.7, 1.0)
        pieces = int(self._piece_accumulator)
        self._piece_accumulator -= pieces
        for _ in range(pieces):
            if random.random() < self.REJECT_PROBABILITY:
                self.reject += 1
            else:
                self.good += 1

    def _update_process_variables(self) -> None:
        running = self.state == CORRIENDO
        target_temp = 55.0 if running else self.AMBIENT_TEMP
        # Sobrecalentamiento ocasional: sube hacia 90 °C durante 15-30 s (dispara la alarma).
        if running and self._overheat_ticks == 0 and random.random() < 0.003:
            self._overheat_ticks = random.randint(15, 30)
        if self._overheat_ticks > 0:
            target_temp = 90.0
            self._overheat_ticks -= 1
        self.temperature += (target_temp - self.temperature) * 0.15 + random.gauss(0, 0.4)

        target_pressure = 4.0 if running else 0.4
        self.pressure += (target_pressure - self.pressure) * 0.3 + random.gauss(0, 0.05)


# ── PASO 3 · Espacio de direcciones OPC UA ───────────────────────────────────
async def build_address_space(server: Server) -> dict:
    """Crea Linea1 y una variable por (equipo, tag). NodeId de texto: 'Llenadora.State'."""
    idx = await server.register_namespace(NAMESPACE_URI)
    line = await server.nodes.objects.add_object(idx, "Linea1")
    nodes: dict = {}
    for machine in MACHINE_NAMES:
        nodes[machine] = {}
        for tag, initial, vtype in TAGS:
            identifier = f"{machine}.{tag}"
            nodes[machine][tag] = await line.add_variable(
                ua.NodeId(identifier, idx), ua.QualifiedName(identifier, idx), initial, vtype
            )
    return nodes


async def publish(machine: SimulatedMachine, nodes: dict) -> None:
    """Escribe los valores actuales de la máquina en sus nodos."""
    await nodes["State"].write_value(int(machine.state))
    await nodes["GoodCount"].write_value(int(machine.good))
    await nodes["RejectCount"].write_value(int(machine.reject))
    await nodes["Temperature"].write_value(round(machine.temperature, 2))
    await nodes["Pressure"].write_value(round(machine.pressure, 3))


# ── PASO 4 · Ciclo principal ─────────────────────────────────────────────────
async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("asyncua").setLevel(logging.WARNING)

    server = Server()
    await server.init()
    server.set_endpoint(ENDPOINT)
    server.set_server_name("Simulador Linea 1")
    nodes = await build_address_space(server)
    machines = [SimulatedMachine(name) for name in MACHINE_NAMES]

    async with server:
        log.info("Servidor OPC UA escuchando en %s", ENDPOINT)
        while True:
            for machine in machines:
                machine.step()
                await publish(machine, nodes[machine.name])
            await asyncio.sleep(TICK_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
