"""Historial y operaciones del laboratorio de voz en una SQLite exclusiva."""

import fcntl
import json
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from calling_repository import VoiceSessionQuotaExceededError, timestamp
from notification_schema import doctor_notifications_schema, migrate_doctor_notifications


TABLES = {"voice_profiles", "voice_sessions", "voice_turns", "voice_tool_calls", "voice_actions", "voice_appointments", "lab_text_messages",
          "voice_notification_events", "doctor_notifications", "doctor_notification_attempts", "sqlite_sequence"}
HISTORY_SEARCH_LIMIT = 6
HISTORY_SNIPPET_CHARACTERS = 600


def _normalize_history_text(text):
    return "".join(char for char in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(char))


def _history_timestamp(value):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")
    except (TypeError, ValueError, OverflowError):
        return None


def _history_excerpt(text, terms):
    position = 0
    if terms:
        match_at = _normalize_history_text(text).find(terms[0])
        normalized_length = 0
        for index, char in enumerate(text):
            normalized_length += len(_normalize_history_text(char))
            if normalized_length > match_at:
                position = index
                break
    start = max(0, position - 120)
    end = min(len(text), start + HISTORY_SNIPPET_CHARACTERS - 2)
    return (("…" if start else "") + text[start:end] + ("…" if end < len(text) else ""),
            start > 0 or end < len(text))


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
                    CREATE TABLE IF NOT EXISTS voice_notification_events (
                        action_id TEXT PRIMARY KEY REFERENCES voice_actions(action_id),
                        session_id TEXT NOT NULL REFERENCES voice_sessions(session_id),
                        event_json TEXT NOT NULL, patient_name TEXT,
                        start_sequence INTEGER NOT NULL, end_sequence INTEGER NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','sent'))
                    );
                """)
                db.executescript(doctor_notifications_schema(patient_references=False))
                migrate_doctor_notifications(db)
                session_columns = {row["name"] for row in db.execute("PRAGMA table_info(voice_sessions)")}
                if "notification_start_sequence" not in session_columns:
                    db.execute("ALTER TABLE voice_sessions ADD COLUMN notification_start_sequence INTEGER NOT NULL DEFAULT 0")
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

    def transaction(self):
        """Adaptador de la bandeja compartida, sin abrir la base de pacientes."""
        return self.connection()

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
            db.execute("""INSERT INTO voice_sessions
                (session_id,profile,state,reason,created_at,updated_at,metrics_json)
                VALUES (?,?,'active',NULL,?,?, '{}')""", (session_id, profile, now, now))

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

    def search_history(self, profile, *, exclude_session_id, query="", start_date=None,
                       end_date=None, channel=None, timezone_name="UTC"):
        """Consulta acotada del perfil del servidor; fechas referidas a la sesion."""
        if not isinstance(query, str) or len(query) > 120:
            raise ValueError("El tema de busqueda debe tener hasta 120 caracteres")
        terms = _normalize_history_text(query).split()
        if len(terms) > 8:
            raise ValueError("Consulta hasta ocho palabras por busqueda")
        if channel is not None and (not isinstance(channel, str) or channel not in {"voice", "text"}):
            raise ValueError("El canal debe ser voice o text")
        for value in (start_date, end_date):
            if value is not None and (not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)):
                raise ValueError("Las fechas de historial deben usar YYYY-MM-DD")
        try:
            first = date.fromisoformat(start_date) if start_date is not None else None
            last = date.fromisoformat(end_date) if end_date is not None else None
            after_last = last + timedelta(days=1) if last is not None else None
        except (ValueError, OverflowError):
            raise ValueError("Las fechas de historial no son validas") from None
        if first is not None and last is not None and first > last:
            raise ValueError("La fecha inicial no puede ser posterior a la final")
        local_timezone = ZoneInfo(timezone_name)
        conditions = ["s.profile=?", "s.session_id<>?"]
        parameters = [profile, exclude_session_id]
        for term in terms:
            conditions.append("instr(history_normalize(t.transcript),?)>0")
            parameters.append(term)
        if channel is not None:
            conditions.append("t.channel=?")
            parameters.append(channel)
        if first is not None:
            conditions.append("history_timestamp(s.created_at)>=?")
            parameters.append(_history_timestamp(datetime.combine(first, time.min, local_timezone).isoformat()))
        if after_last is not None:
            conditions.append("history_timestamp(s.created_at)<?")
            parameters.append(_history_timestamp(datetime.combine(after_last, time.min, local_timezone).isoformat()))
        if any(value is None for value in parameters):
            raise ValueError("Las fechas de historial no son validas")
        with self.connection() as db:
            db.execute("PRAGMA query_only=ON")
            db.create_function("history_normalize", 1, _normalize_history_text, deterministic=True)
            db.create_function("history_timestamp", 1, _history_timestamp, deterministic=True)
            rows = db.execute("""SELECT t.session_id,s.state AS session_state,s.created_at AS session_started_at,
                t.item_id,t.sequence,t.channel,t.role,t.transcript,t.state,t.generation_state,t.generated_ms,t.emitted_ms
                FROM voice_turns t JOIN voice_sessions s USING(session_id) WHERE """ + " AND ".join(conditions) + """
                ORDER BY history_timestamp(s.created_at) DESC,s.session_id DESC,t.sequence DESC,t.item_id DESC LIMIT ?""",
                (*parameters, HISTORY_SEARCH_LIMIT + 1)).fetchall()
        fragments = []
        for row in rows[:HISTORY_SEARCH_LIMIT]:
            fragment = dict(row)
            text = fragment.pop("transcript")
            fragment["transcript_available"] = bool(text)
            fragment["text"], fragment["truncated"] = _history_excerpt(text, terms)
            if not text:
                fragment["text"] = "[Intervencion sin transcripcion disponible.]" if row["role"] == "user" else "[Respuesta sin texto disponible.]"
            fragments.append(fragment)
        return {"fragments": fragments, "has_more": len(rows) > HISTORY_SEARCH_LIMIT,
                "date_basis": "session_started_at", "date_precision": "session", "timezone": timezone_name}

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

    def save_action_result(self, session_id: str, action_id: str, call_id: str, result: dict, profile: str, appointments: list[dict] | None, patient_name: str | None,
                           notification_event=None):
        with self.connection() as db:
            if appointments is not None:
                db.execute("DELETE FROM voice_appointments WHERE profile=?", (profile,))
                db.executemany("INSERT INTO voice_appointments VALUES (?,?,?)", ((profile, item["id"], json.dumps(item, ensure_ascii=False)) for item in appointments))
            if patient_name:
                db.execute("UPDATE voice_profiles SET patient_name=? WHERE profile=?", (patient_name, profile))
            db.execute("UPDATE voice_actions SET state=? WHERE session_id=? AND action_id=?", ("completed" if result.get("ok") else "failed", session_id, action_id))
            db.execute("UPDATE voice_tool_calls SET state='completed',result_json=? WHERE session_id=? AND call_id=?", (json.dumps(result, ensure_ascii=False), session_id, call_id))
            if notification_event is not None and result.get("ok"):
                name = db.execute("SELECT patient_name FROM voice_profiles WHERE profile=?", (profile,)).fetchone()[0]
                start = db.execute("SELECT COALESCE(MAX(end_sequence),0) FROM voice_notification_events WHERE session_id=?", (session_id,)).fetchone()[0]
                workflow_start = db.execute("SELECT notification_start_sequence FROM voice_sessions WHERE session_id=?", (session_id,)).fetchone()[0]
                start = max(start, workflow_start)
                db.execute("""INSERT OR IGNORE INTO voice_notification_events
                    (action_id,session_id,event_json,patient_name,start_sequence,end_sequence)
                    VALUES (?,?,?,?,?,?)""", (action_id, session_id, notification_event.to_json(), name,
                                               start, notification_event.incoming_message_id))

    def last_sequence(self, session_id):
        with self.connection() as db:
            return db.execute("SELECT COALESCE(MAX(sequence),1) FROM voice_turns WHERE session_id=?", (session_id,)).fetchone()[0]

    def pending_notifications(self):
        with self.connection() as db:
            return [dict(row) for row in db.execute("""SELECT e.* FROM voice_notification_events e
                WHERE e.status='pending' OR EXISTS (
                    SELECT 1 FROM doctor_notifications n
                    WHERE n.event_key LIKE 'voice:' || e.session_id || ':' || e.action_id || ':%'
                      AND n.status IN ('pending','failed','sending') AND n.event_json IS NULL)
                ORDER BY e.rowid""")]

    def notification_sent(self, action_id):
        with self.connection() as db:
            db.execute("UPDATE voice_notification_events SET status='sent' WHERE action_id=?", (action_id,))

    def notification_context(self, record):
        from notification_trigger import DoctorNotificationContext
        from repositories import MessageRecord

        with self.connection() as db:
            rows = db.execute("""SELECT t.*,s.created_at FROM voice_turns t JOIN voice_sessions s USING(session_id)
                WHERE t.session_id=? AND t.sequence>? AND t.sequence<=?
                AND (t.role='user' OR t.state='completed')
                ORDER BY t.sequence DESC""",
                (record["session_id"], record["start_sequence"], record["end_sequence"])).fetchall()
        history = tuple(MessageRecord(id=row["sequence"], conversation_id=1,
            direction="incoming" if row["role"] == "user" else "outgoing", provider_message_id=None,
            text=row["transcript"], message_type=row["channel"],
            status="received" if row["role"] == "user" else "sent",
            reply_to_message_id=row["sequence"] if row["role"] != "user" else None,
            created_at=row["created_at"]) for row in reversed(rows) if row["transcript"])
        return DoctorNotificationContext(record["patient_name"], history)

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

    def replace_workflow(self, profile, session_id=None):
        with self.connection() as db:
            db.execute("""UPDATE voice_actions SET state='superseded' WHERE state IN ('pending','invalidated')
                AND session_id IN (SELECT session_id FROM voice_sessions WHERE profile=?)""", (profile,))
            if session_id is not None:
                # La ultima entrada del paciente inicia la gestion nueva. Una
                # salida/placeholder del asistente puede tener secuencia mayor.
                db.execute("""UPDATE voice_sessions SET notification_start_sequence=(
                    SELECT MAX(COALESCE(MAX(sequence),1)-1,0) FROM voice_turns WHERE session_id=? AND role='user'
                    ) WHERE session_id=? AND profile=?""", (session_id, session_id, profile))
