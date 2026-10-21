"""Ordena interrupcion/cierre y reclamacion durable, tambien entre hilos SQLite."""

import threading
from contextlib import contextmanager


class VoiceAuthorization:
    def __init__(self):
        self._lock = threading.RLock()
        self.generation = 0
        self.closed = False

    def supersede(self, generation: int):
        with self._lock:
            self.generation = generation

    def close(self):
        with self._lock:
            self.closed = True

    def valid(self, generation: int) -> bool:
        with self._lock:
            return not self.closed and generation == self.generation

    @contextmanager
    def claim(self, generation: int):
        # Se toma DESPUES del bloqueo de escritura SQL. Mientras SQLite espera,
        # colgar o empezar otra intervencion puede revocar sin esperar al escritor.
        with self._lock:
            yield not self.closed and generation == self.generation
