"""Persistencia exclusiva del laboratorio; nunca abre la base de pacientes."""

import fcntl
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


TERMINAL_STATES = frozenset({"ended", "failed", "interrupted"})


class CallCapacityError(RuntimeError):
    pass


class VoiceSessionQuotaExceededError(ValueError):
    """El perfil ficticio alcanzó su cuota configurada de sesiones Realtime."""

    def __init__(self, used: int, maximum: int) -> None:
        self.used = used
        self.maximum = maximum
        super().__init__(f"Cuota de sesiones de voz agotada ({used}/{maximum})")


class CallNotFoundError(LookupError):
    pass


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class CallingRepository:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path).expanduser().resolve()
        self._lock_file = None

    @contextmanager
    def _connect(self):
        # No bloquear el event loop de audio durante segundos por otro escritor.
        connection = sqlite3.connect(self.path, timeout=0.1)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def start(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_file = self.path.with_suffix(self.path.suffix + ".lock").open("a+b")
        try:
            fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self._connect() as connection:
                tables = {
                    row[0] for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                if tables - {"lab_call_sessions", "lab_call_events", "sqlite_sequence"}:
                    raise ValueError("El laboratorio requiere una base SQLite exclusiva")
                connection.executescript("""
                    CREATE TABLE IF NOT EXISTS lab_call_sessions (
                        session_id TEXT PRIMARY KEY,
                        state TEXT NOT NULL CHECK (state IN (
                            'received', 'negotiating', 'active', 'ending',
                            'ended', 'failed', 'interrupted'
                        )),
                        greeting_state TEXT NOT NULL DEFAULT 'prepared' CHECK (
                            greeting_state IN ('prepared', 'playing', 'completed', 'interrupted', 'failed')
                        ),
                        reason TEXT,
                        metrics_json TEXT NOT NULL DEFAULT '{}',
                        resources_released INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE UNIQUE INDEX IF NOT EXISTS one_active_laboratory_call
                    ON lab_call_sessions ((1))
                    WHERE state IN ('received', 'negotiating', 'active', 'ending');
                    CREATE TABLE IF NOT EXISTS lab_call_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL REFERENCES lab_call_sessions(session_id),
                        kind TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                """)
                rows = connection.execute(
                    "SELECT session_id FROM lab_call_sessions WHERE state NOT IN ('ended','failed','interrupted')"
                ).fetchall()
                for row in rows:
                    connection.execute(
                        """UPDATE lab_call_sessions SET state='interrupted', reason='process_restart',
                        greeting_state=CASE WHEN greeting_state='playing' THEN 'interrupted' ELSE greeting_state END,
                        resources_released=1, updated_at=? WHERE session_id=?""",
                        (timestamp(), row[0]),
                    )
                    self._event(connection, row[0], "process_restart")
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if self._lock_file is not None:
            self._lock_file.close()
            self._lock_file = None

    @staticmethod
    def _event(connection, session_id: str, kind: str) -> None:
        connection.execute(
            "INSERT INTO lab_call_events(session_id, kind, created_at) VALUES (?,?,?)",
            (session_id, kind, timestamp()),
        )

    def claim(self) -> dict:
        session_id = uuid4().hex
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO lab_call_sessions(session_id,state,created_at,updated_at) VALUES (?,'received',?,?)",
                    (session_id, timestamp(), timestamp()),
                )
                self._event(connection, session_id, "received")
        except sqlite3.IntegrityError as error:
            raise CallCapacityError("Hay una sesion de laboratorio activa") from error
        return self.get(session_id)

    def get(self, session_id: str) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM lab_call_sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            if row is None:
                raise CallNotFoundError(session_id)
            result = dict(row)
            result["metrics"] = json.loads(result.pop("metrics_json"))
            result["resources_released"] = bool(result["resources_released"])
            result["mode"] = "laboratory"
            result["events"] = [
                dict(event) for event in connection.execute(
                    "SELECT kind,created_at FROM lab_call_events WHERE session_id=? ORDER BY id",
                    (session_id,),
                )
            ]
            return result

    def transition(self, session_id: str, state: str) -> None:
        with self._connect() as connection:
            changed = connection.execute(
                """UPDATE lab_call_sessions SET state=?,updated_at=? WHERE session_id=?
                AND state NOT IN ('ended','failed','interrupted') AND state!=?""",
                (state, timestamp(), session_id, state),
            ).rowcount
            if changed:
                self._event(connection, session_id, state)

    def greeting(self, session_id: str, state: str) -> None:
        with self._connect() as connection:
            previous = "prepared" if state == "playing" else "playing"
            changed = connection.execute(
                """UPDATE lab_call_sessions SET greeting_state=?,updated_at=? WHERE session_id=?
                AND state='active' AND greeting_state=?""",
                (state, timestamp(), session_id, previous),
            ).rowcount
            if changed:
                self._event(connection, session_id, "greeting_" + state)

    def end(self, session_id: str, state: str, reason: str, metrics: dict, released: bool, greeting_state: str | None = None) -> None:
        with self._connect() as connection:
            connection.execute(
                """UPDATE lab_call_sessions SET state=?,reason=?,metrics_json=?,resources_released=?,
                greeting_state=COALESCE(?, CASE WHEN greeting_state='playing' THEN
                    CASE WHEN ?='failed' THEN 'failed' ELSE 'interrupted' END
                    ELSE greeting_state END),
                updated_at=? WHERE session_id=?""",
                (state, reason, json.dumps(metrics), int(released), greeting_state, state, timestamp(), session_id),
            )
            self._event(connection, session_id, reason)
