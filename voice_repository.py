"""Historial y operaciones del laboratorio de voz en una SQLite exclusiva."""

import fcntl
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from calling_repository import VoiceSessionQuotaExceededError, timestamp


TABLES = {"voice_profiles", "voice_sessions", "voice_turns", "voice_tool_calls", "voice_actions", "voice_appointments", "lab_text_messages"}


class VoiceRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self._lock = None

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=0.1)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        finally:
            db.close()

    def start(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = self.path.with_suffix(self.path.suffix + ".lock").open("a+b")
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.connection() as db:
                tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if tables - TABLES:
                    raise ValueError("VOICE_DATABASE_PATH requiere una base exclusiva del laboratorio de voz")
                db.executescript("""
                    CREATE TABLE IF NOT EXISTS voice_profiles (
                        profile TEXT PRIMARY KEY, patient_name TEXT, blocked INTEGER NOT NULL DEFAULT 0
                    );
                    CREATE TABLE IF NOT EXISTS voice_sessions (
                        session_id TEXT PRIMARY KEY, profile TEXT NOT NULL REFERENCES voice_profiles(profile),
                        state TEXT NOT NULL, reason TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                        metrics_json TEXT NOT NULL DEFAULT '{}'
                    );
                    CREATE TABLE IF NOT EXISTS voice_turns (
                        session_id TEXT NOT NULL REFERENCES voice_sessions(session_id), item_id TEXT NOT NULL,
                        role TEXT NOT NULL, transcript TEXT NOT NULL DEFAULT '', state TEXT NOT NULL,
                        sequence INTEGER NOT NULL, PRIMARY KEY(session_id,item_id)
                    );
                    CREATE TABLE IF NOT EXISTS voice_tool_calls (
                        session_id TEXT NOT NULL REFERENCES voice_sessions(session_id), call_id TEXT NOT NULL,
                        request_json TEXT NOT NULL, result_json TEXT, state TEXT NOT NULL,
                        PRIMARY KEY(session_id,call_id)
                    );
                    CREATE TABLE IF NOT EXISTS voice_actions (
                        action_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES voice_sessions(session_id),
                        turn_id TEXT NOT NULL, request_json TEXT NOT NULL, prompt TEXT NOT NULL,
                        state TEXT NOT NULL, created_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS voice_appointments (
                        profile TEXT NOT NULL REFERENCES voice_profiles(profile), appointment_id TEXT NOT NULL,
                        payload TEXT NOT NULL, PRIMARY KEY(profile,appointment_id)
                    );
                    CREATE TABLE IF NOT EXISTS lab_text_messages (
                        profile TEXT NOT NULL REFERENCES voice_profiles(profile), message_id TEXT NOT NULL,
                        body TEXT NOT NULL, result_json TEXT, state TEXT NOT NULL,
                        PRIMARY KEY(profile,message_id)
                    );
                """)
                columns = {row["name"] for row in db.execute("PRAGMA table_info(voice_turns)")}
                for name, definition in {
                    "channel": "TEXT NOT NULL DEFAULT 'voice'",
                    "generation_state": "TEXT NOT NULL DEFAULT 'unknown'",
                    "generated_ms": "REAL NOT NULL DEFAULT 0",
                    "emitted_ms": "REAL NOT NULL DEFAULT 0",
                }.items():
                    if name not in columns:
                        db.execute(f"ALTER TABLE voice_turns ADD COLUMN {name} {definition}")
                db.execute("UPDATE voice_profiles SET blocked=1 WHERE profile IN (SELECT profile FROM voice_sessions WHERE session_id IN (SELECT session_id FROM voice_actions WHERE state='executing'))")
                db.execute("UPDATE voice_actions SET state='uncertain' WHERE state='executing'")
                db.execute("UPDATE voice_actions SET state='invalidated' WHERE state='pending'")
                db.execute("UPDATE voice_tool_calls SET state='uncertain' WHERE state='processing'")
                db.execute("UPDATE voice_turns SET state='interrupted' WHERE state IN ('generating','playing','prepared')")
                db.execute("UPDATE voice_turns SET generation_state='unknown' WHERE generation_state='generating'")
                db.execute("UPDATE voice_sessions SET state='interrupted',reason='process_restart',updated_at=? WHERE state='active'", (timestamp(),))
                db.execute("UPDATE lab_text_messages SET state='interrupted',result_json=? WHERE state='processing'", (
                    json.dumps({"state": "interrupted", "reply": "La solicitud se interrumpio; inicia otro mensaje sin repetir operaciones anteriores."}),))
        except BaseException:
            self.close()
            raise

    def close(self):
        if self._lock is not None:
            self._lock.close()
            self._lock = None

    def begin(self, session_id: str, profile: str, maximum_sessions: int | None):
        with self.connection() as db:
            db.execute("INSERT OR IGNORE INTO voice_profiles(profile) VALUES (?)", (profile,))
            blocked = db.execute("SELECT blocked FROM voice_profiles WHERE profile=?", (profile,)).fetchone()[0]
            uncertain = db.execute("SELECT 1 FROM voice_actions a JOIN voice_sessions s USING(session_id) WHERE s.profile=? AND a.state IN ('executing','uncertain') LIMIT 1", (profile,)).fetchone()
            if blocked or uncertain:
                raise ValueError("El perfil requiere conciliar una operacion incierta")
            count = db.execute("SELECT COUNT(*) FROM voice_sessions WHERE profile=?", (profile,)).fetchone()[0]
            if maximum_sessions is not None and count >= maximum_sessions:
                raise VoiceSessionQuotaExceededError(count, maximum_sessions)
            now = timestamp()
            db.execute("INSERT INTO voice_sessions VALUES (?,?,'active',NULL,?,?, '{}')", (session_id, profile, now, now))

    def finish(self, session_id: str, reason: str, metrics: dict):
        with self.connection() as db:
            db.execute("UPDATE voice_sessions SET state='ended',reason=?,metrics_json=?,updated_at=? WHERE session_id=?", (reason, json.dumps(metrics), timestamp(), session_id))
            db.execute("UPDATE voice_actions SET state='invalidated' WHERE session_id=? AND state='pending'", (session_id,))
            db.execute("UPDATE voice_turns SET state='interrupted' WHERE session_id=? AND state IN ('generating','playing','prepared')", (session_id,))
            db.execute("UPDATE voice_turns SET generation_state='unknown' WHERE session_id=? AND generation_state='generating'", (session_id,))
            db.execute("UPDATE voice_turns SET state='transcription_missing' WHERE session_id=? AND role='user' AND transcript='' AND state='received'", (session_id,))

    def turn(self, session_id: str, item_id: str, role: str, transcript: str | None = None, state: str | None = None, channel: str = "voice", sequence: int | None = None):
        if channel not in {"voice", "text"}:
            raise ValueError("Canal de laboratorio invalido")
        with self.connection() as db:
            if sequence is None:
                sequence = db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM voice_turns WHERE session_id=?", (session_id,)).fetchone()[0]
            db.execute("""INSERT OR IGNORE INTO voice_turns
                (session_id,item_id,role,transcript,state,sequence,channel,generation_state)
                VALUES (?,?,?,'',?,?,?,?)""", (session_id, item_id, role, state or "received", sequence, channel,
                                               "generating" if role == "assistant" else "not_applicable"))
            if transcript is not None:
                db.execute("UPDATE voice_turns SET transcript=? WHERE session_id=? AND item_id=?", (transcript[:8000], session_id, item_id))
            if state is not None:
                db.execute("""UPDATE voice_turns SET state=CASE
                    WHEN state='interrupted' THEN state
                    WHEN state='completed' AND ? IN ('playing','generating','received') THEN state
                    ELSE ? END WHERE session_id=? AND item_id=?""", (state, state, session_id, item_id))

    def progress(self, session_id, item_id, *, generated_ms=None, emitted_ms=None, generation_state=None):
        with self.connection() as db:
            if generated_ms is not None:
                db.execute("UPDATE voice_turns SET generated_ms=MAX(generated_ms,?) WHERE session_id=? AND item_id=?", (generated_ms, session_id, item_id))
            if emitted_ms is not None:
                db.execute("UPDATE voice_turns SET emitted_ms=MAX(emitted_ms,?) WHERE session_id=? AND item_id=?", (emitted_ms, session_id, item_id))
            if generation_state:
                db.execute("""UPDATE voice_turns SET generation_state=CASE
                    WHEN generation_state IN ('completed','cancelled','failed') THEN generation_state
                    ELSE ? END WHERE session_id=? AND item_id=?""", (generation_state, session_id, item_id))

    def history(self, profile: str) -> list[dict]:
        with self.connection() as db:
            rows = db.execute("""SELECT t.role,t.transcript,t.state,t.channel FROM voice_turns t
                JOIN voice_sessions s USING(session_id) WHERE s.profile=?
                ORDER BY s.created_at DESC,t.sequence DESC LIMIT 12""", (profile,)).fetchall()
        result = []
        for row in reversed(rows):
            if row["role"] == "user" and not row["transcript"]:
                text = "[Intervencion de voz sin transcripcion disponible. No inferir su contenido ni usarla como autorizacion.]"
            elif row["role"] == "assistant" and row["state"] != "completed":
                text = "[La respuesta anterior fue interrumpida; no asumir que se emitio completa.]"
            else:
                text = row["transcript"]
            if row["channel"] == "text":
                text = "[Texto de laboratorio] " + text
            result.append({"type": "message", "role": row["role"], "content": [{
                "type": "input_text" if row["role"] == "user" else "output_text", "text": text,
            }]})
        return result

    def turns(self, session_id: str):
        with self.connection() as db:
            return [dict(row) for row in db.execute("SELECT item_id,role,transcript,state,sequence,channel,generation_state,generated_ms,emitted_ms FROM voice_turns WHERE session_id=? ORDER BY sequence DESC LIMIT 20", (session_id,))][::-1]

    def profile_history(self, profile, limit=30):
        with self.connection() as db:
            return [dict(row) for row in db.execute("""SELECT t.*,s.created_at FROM voice_turns t
                JOIN voice_sessions s USING(session_id) WHERE s.profile=?
                ORDER BY s.created_at DESC,t.sequence DESC LIMIT ?""", (profile, limit))][::-1]

    def claim_text(self, profile, message_id, body):
        with self.connection() as db:
            db.execute("INSERT OR IGNORE INTO voice_profiles(profile) VALUES (?)", (profile,))
            row = db.execute("SELECT body,state,result_json FROM lab_text_messages WHERE profile=? AND message_id=?", (profile, message_id)).fetchone()
            if row:
                if row["body"] != body:
                    raise ValueError("message_id reutilizado con otro contenido")
                return False, json.loads(row["result_json"]) if row["result_json"] else {"state": "processing", "reply": "Mensaje en proceso"}
            db.execute("INSERT INTO lab_text_messages VALUES (?,?,?,NULL,'processing')", (profile, message_id, body))
            return True, None

    def finish_text(self, profile, message_id, result):
        with self.connection() as db:
            db.execute("UPDATE lab_text_messages SET state=?,result_json=? WHERE profile=? AND message_id=?", (
                result["state"], json.dumps(result, ensure_ascii=False), profile, message_id))

    def claim_tool(self, session_id: str, call_id: str, request: dict) -> tuple[bool, dict | None]:
        payload = json.dumps(request, sort_keys=True, ensure_ascii=False)
        with self.connection() as db:
            row = db.execute("SELECT request_json,result_json FROM voice_tool_calls WHERE session_id=? AND call_id=?", (session_id, call_id)).fetchone()
            if row:
                if row["request_json"] != payload:
                    raise ValueError("call_id reutilizado con otros argumentos")
                return False, json.loads(row["result_json"]) if row["result_json"] else {"ok": False, "error": "Operacion pendiente o incierta; no repetir"}
            db.execute("INSERT INTO voice_tool_calls VALUES (?,?,?,NULL,'processing')", (session_id, call_id, payload))
        return True, None

    def tool_result(self, session_id: str, call_id: str, result: dict):
        with self.connection() as db:
            db.execute("UPDATE voice_tool_calls SET result_json=?,state='completed' WHERE session_id=? AND call_id=?", (json.dumps(result, ensure_ascii=False), session_id, call_id))

    def propose(self, session_id: str, turn_id: str, request: dict, prompt: str) -> str:
        action_id = uuid4().hex
        with self.connection() as db:
            db.execute("UPDATE voice_actions SET state='invalidated' WHERE session_id=? AND state='pending'", (session_id,))
            db.execute("INSERT INTO voice_actions VALUES (?,?,?,?,?,'pending',?)", (action_id, session_id, turn_id, json.dumps(request, ensure_ascii=False), prompt, timestamp()))
        return action_id

    def invalidate(self, session_id: str):
        with self.connection() as db:
            db.execute("UPDATE voice_actions SET state='invalidated' WHERE session_id=? AND state='pending'", (session_id,))

    def invalidate_action(self, session_id: str, action_id: str):
        with self.connection() as db:
            db.execute("UPDATE voice_actions SET state='invalidated' WHERE session_id=? AND action_id=? AND state='pending'", (session_id, action_id))

    def execute_action(self, session_id: str, action_id: str, authorization, generation: int) -> bool:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            with authorization.claim(generation) as allowed:
                if not allowed:
                    return False
                changed = db.execute("UPDATE voice_actions SET state='executing' WHERE session_id=? AND action_id=? AND state='pending'", (session_id, action_id)).rowcount == 1
                # Mantener la autorizacion hasta hacer durable la reclamacion.
                db.commit()
                return changed

    def save_action_result(self, session_id: str, action_id: str, call_id: str, result: dict, profile: str, appointments: list[dict] | None, patient_name: str | None):
        with self.connection() as db:
            if appointments is not None:
                db.execute("DELETE FROM voice_appointments WHERE profile=?", (profile,))
                db.executemany("INSERT INTO voice_appointments VALUES (?,?,?)", ((profile, item["id"], json.dumps(item, ensure_ascii=False)) for item in appointments))
            if patient_name:
                db.execute("UPDATE voice_profiles SET patient_name=? WHERE profile=?", (patient_name, profile))
            db.execute("UPDATE voice_actions SET state=? WHERE session_id=? AND action_id=?", ("completed" if result.get("ok") else "failed", session_id, action_id))
            db.execute("UPDATE voice_tool_calls SET state='completed',result_json=? WHERE session_id=? AND call_id=?", (json.dumps(result, ensure_ascii=False), session_id, call_id))

    def appointments(self, profile: str) -> list[dict]:
        with self.connection() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT payload FROM voice_appointments WHERE profile=?", (profile,))]

    def latest_action(self, profile):
        with self.connection() as db:
            row = db.execute("""SELECT a.* FROM voice_actions a JOIN voice_sessions s USING(session_id)
                WHERE s.profile=? ORDER BY a.created_at DESC LIMIT 1""", (profile,)).fetchone()
        if not row or row["state"] not in {"pending", "invalidated"}:
            return None
        return {**json.loads(row["request_json"]), "action_id": row["action_id"], "session_id": row["session_id"], "state": row["state"]}

    def replace_workflow(self, profile):
        with self.connection() as db:
            db.execute("""UPDATE voice_actions SET state='superseded' WHERE state IN ('pending','invalidated')
                AND session_id IN (SELECT session_id FROM voice_sessions WHERE profile=?)""", (profile,))
