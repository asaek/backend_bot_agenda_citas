# WhatsApp Chatbot

Etapa 4: agente LLM basico con un contrato independiente del proveedor,
persistencia conversacional y pruebas sin consumir API mediante un
`FakeLLMProvider`.

## 1. Instalar dependencias

```bash
uv sync
```

## 2. Configurar variables de entorno

El archivo `.env` se carga automaticamente desde la raiz del proyecto y esta
excluido de Git. Usa `.env.example` como referencia y reemplaza sus valores por
los reales. El Verify Token debe coincidir con el configurado en Meta.

Las variables exportadas en la shell tienen prioridad sobre `.env`.

`DATABASE_PATH` define la ruta de la base SQLite. Si no se configura, se usa
`data/chatbot.sqlite3`. La carpeta `data/` esta excluida de Git.

El adaptador compatible con OpenAI usa estas variables adicionales:

- `LLM_PROVIDER=groq`
- `LLM_API_KEY`
- `LLM_MODEL`
- `LLM_BASE_URL=https://api.groq.com/openai/v1`
- `LLM_TIMEOUT_SECONDS=20`
- `LLM_MAX_HISTORY_MESSAGES=30`
- `LLM_MAX_OUTPUT_TOKENS=500`
- `LLM_MAX_RESPONSE_CHARACTERS=4000`
- `LLM_MAX_TOOL_ITERATIONS=3`

Para usar OpenRouter cambia `LLM_PROVIDER` a `openrouter`, `LLM_API_KEY`,
`LLM_MODEL` y `LLM_BASE_URL=https://openrouter.ai/api/v1`.

El agente actual genera texto y puede ejecutar `ToolCall` mediante un
`AgentOrchestrator` y un `ToolExecutor` configurado por `main.py`. El runtime usa
`FakeCalendarProvider` y horario laboral de lunes a viernes, 09:00-17:00 UTC,
para probar la agenda sin servicios externos cuando `CALENDAR_PROVIDER=fake`. El
limite de llamadas se configura con `LLM_MAX_TOOL_ITERATIONS`. RAG y memoria
semantica siguen fuera del alcance. La suite automatizada usa proveedores falsos y
no requiere credenciales externas.

Para activar Google Calendar para todas las operaciones, cambia
`CALENDAR_PROVIDER=google` y configura:

Durante la migracion incremental, conserva `CALENDAR_PROVIDER=fake` y usa
`CALENDAR_AVAILABILITY_PROVIDER=google` para conectar solamente
`check_availability`. Si no se configura este selector, disponibilidad usa el
proveedor principal.

- `GOOGLE_CALENDAR_IDS`: uno o varios IDs separados por comas, hasta 50.
- `GOOGLE_CALENDAR_AUTH=service_account` y `GOOGLE_SERVICE_ACCOUNT_FILE`, o
  `GOOGLE_CALENDAR_AUTH=oauth` con client ID, client secret y refresh/access token.
- `GOOGLE_SERVICE_ACCOUNT_SUBJECT` solo cuando se use delegacion de dominio.
- `GOOGLE_CALENDAR_TIMEZONE`, `GOOGLE_CALENDAR_BASE_URL` y
  `GOOGLE_CALENDAR_TIMEOUT_SECONDS`.
- `BUSINESS_WORKDAYS`, `BUSINESS_HOURS_START` y `BUSINESS_HOURS_END` para definir
  los dias y el horario laboral sin modificar codigo.

El adaptador consulta `freeBusy`, lista eventos paginados y administra solo los
eventos con propiedades privadas `managed_by=whatsapp_chatbot` y `patient_id`.
Cada cita ocupa 30 minutos y conserva el `PatientScope` resuelto por el backend.
Los secretos deben vivir fuera del repositorio, por ejemplo en variables de
entorno y archivos montados como secretos.

La siguiente funcionalidad planificada es `011-doctor-notifications`. Cuando se
implemente, una cita agendada, modificada o cancelada correctamente generara un
unico mensaje para el doctor. El mensaje incluira el evento, los datos de la cita,
el paciente, el telefono, el resumen conversacional y las señales de prioridad
disponibles. El resumen sera contenido obligatorio de esos tres mensajes y no se
enviara de forma independiente.

Cuando se usa Google, SQLite conserva la identidad local de cada cita en la tabla
`appointments`. El ID que reciben las herramientas es el `id` interno; el
`google_event_id` queda separado junto con `calendar_id`, paciente, estado, fechas,
motivo y `last_synced_at`. Google Calendar sigue siendo la fuente de verdad del
estado de la agenda.

El incremento verificado define el modelo de dominio, los contratos tipados de
las cinco herramientas, la validacion previa al proveedor, los errores publicos,
`CalendarProvider`, `FakeCalendarProvider` y `ToolExecutor`. El adaptador
`GoogleCalendarProvider` y su seleccion explicita estan implementados y verificados
con HTTP simulado en el mirror de Raspberry Pi.

El webhook crea el proveedor, recupera el historial desde `ConversationService`,
genera la respuesta, ejecuta herramientas mediante el `ToolExecutor` configurado,
la envia por WhatsApp y registra el resultado. Un fallo de
generacion o envio queda marcado como `failed` para permitir un reintento.

Las notificaciones al doctor todavia no forman parte de este runtime. Su alcance,
diseno y cortes estan documentados en `docs/specs/011-doctor-notifications/`.

## 3. Iniciar el servidor

```bash
uv run uvicorn main:app --reload
```

El backend queda disponible en <http://127.0.0.1:8000>.

## 4. Probar localmente

En otra terminal, comprueba el estado del backend:

```bash
curl http://127.0.0.1:8000/
```

Simula la verificacion que realizara Meta:

```bash
curl "http://127.0.0.1:8000/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=mi-token-secreto&hub.challenge=12345"
```

La respuesta debe ser `12345`.

Simula un evento entrante de WhatsApp:

```bash
curl -X POST http://127.0.0.1:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{"object":"whatsapp_business_account","entry":[{"changes":[{"value":{"messages":[{"from":"5491100000000","id":"wamid.test","type":"text","text":{"body":"Hola"}}]}}]}]}'
```

La respuesta debe ser `{"status":"ok"}`. El backend extrae el remitente, el ID,
el tipo y el texto, identifica o crea el paciente de prueba, construye el
contexto, genera la respuesta, la envia y la guarda como `sent`.

Un segundo evento con el mismo valor de `from` reutiliza el paciente y la
conversacion activa. Si Meta reenvia el mismo `id`, el backend no duplica la
respuesta cuando ya fue enviada.

Para probar persistencia, continuidad, idempotencia y la construccion de la
solicitud de salida sin enviar un mensaje real ni consumir un LLM:

```bash
uv run python -m unittest discover -s tests -v
```

La suite usa un proveedor LLM falso, un cliente falso de WhatsApp y una base
SQLite temporal. Tambien verifica la transformacion del historial, el mensaje
actual, las respuestas `sent`, los errores del LLM, los webhooks duplicados y la
verificacion de Meta.

## Endpoints

- `GET /`: comprobacion sencilla del servidor.
- `GET /webhook/whatsapp`: verificacion solicitada por Meta.
- `POST /webhook/whatsapp`: recepcion de eventos enviados por Meta, persistencia
  de mensajes y respuesta generada por el LLM para mensajes de texto.

Los eventos que no sean mensajes de texto, como estados, imagenes o audios, se
ignoran temporalmente. Las credenciales solo deben existir como variables de
entorno en la Raspberry Pi:

- `WHATSAPP_VERIFY_TOKEN`
- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`

`DATABASE_PATH` no es una credencial, pero debe apuntar a una ruta persistente en
la Raspberry Pi.
