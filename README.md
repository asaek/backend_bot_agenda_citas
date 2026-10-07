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

El adaptador compatible con OpenAI usa `LLM_PROVIDER` para seleccionar `groq`,
`openai` u `openrouter`. Configura las credenciales y modelos por separado:

- `GROQ_API_KEY` y `GROQ_MODEL`
- `OPENAI_API_KEY` y `OPENAI_MODEL`
- `OPENROUTER_API_KEY` y `OPENROUTER_MODEL` (opcional)

Las URLs oficiales se seleccionan automaticamente. Groq y OpenRouter usan
`/v1/chat/completions`; OpenAI usa `/v1/responses`. Los endpoints se pueden
reemplazar con `GROQ_BASE_URL`, `OPENAI_BASE_URL` o `OPENROUTER_BASE_URL`.
Para cambiar entre Groq y OpenAI, configura ambos pares de credenciales y modelos,
cambia solamente `LLM_PROVIDER` y reinicia el backend. La clave y el consumo de la API
de OpenAI se administran por separado de una suscripcion de ChatGPT.

`LLM_MODEL` (o el `<PROVIDER>_MODEL` correspondiente) se envia sin transformaciones
como el campo `model` de la solicitud. Debe ser el ID reconocido por el proveedor
seleccionado y admitir su endpoint y function calling.

Tambien puedes usar `LLM_API_KEY` y `LLM_MODEL` para las credenciales del proveedor
activo. Por ejemplo, con `LLM_PROVIDER=openai`, coloca en ellas la clave de OpenAI y
el modelo correspondiente. Al cambiar de proveedor con esta configuracion, actualiza
tambien la clave y el modelo. Las variables por proveedor tienen precedencia y permiten
cambiar solo `LLM_PROVIDER` cuando ambos proveedores ya estan configurados. La variable
generica `LLM_BASE_URL` se mantiene como compatibilidad para Groq y OpenRouter; OpenAI
usa su URL oficial salvo que se configure `OPENAI_BASE_URL`.

Ejemplo de configuracion con las variables genericas:

```env
LLM_PROVIDER=openai
LLM_API_KEY=tu-clave-de-OpenAI
LLM_MODEL=gpt-oss-20b
```

El identificador `openai/gpt-oss-20b` corresponde al nombre usado por Groq. En OpenAI,
el ID oficial es `gpt-oss-20b`; la [documentacion del modelo](https://developers.openai.com/api/docs/models/gpt-oss-20b)
indica que utiliza Responses API y soporta function calling. El adaptador selecciona
esa ruta cuando `LLM_PROVIDER=openai`, y conserva Chat Completions para Groq y OpenRouter.

- `LLM_PROVIDER=groq`
- `LLM_TIMEOUT_SECONDS=20`
- `LLM_MAX_HISTORY_MESSAGES=30`
- `LLM_MAX_OUTPUT_TOKENS=500`
- `LLM_MAX_RESPONSE_CHARACTERS=4000`
- `LLM_MAX_TOOL_ITERATIONS=3`
- `LLM_REASON_EVALUATION_ENABLED=true`

El agente actual genera texto y puede ejecutar `ToolCall` mediante un
`AgentOrchestrator` y un `ToolExecutor` configurado por `main.py`. El runtime usa
`FakeCalendarProvider` y horario laboral de lunes a viernes, 09:00-17:00 UTC,
para probar la agenda sin servicios externos cuando `CALENDAR_PROVIDER=fake`. El
limite de llamadas se configura con `LLM_MAX_TOOL_ITERATIONS`. RAG y memoria
semantica siguen fuera del alcance. La suite automatizada usa proveedores falsos y
no requiere credenciales externas. Las respuestas con varias citas se envian como
listas simples compatibles con WhatsApp; las tablas Markdown se convierten antes
de enviarse.

Cuando `LLM_REASON_EVALUATION_ENABLED=true`, el backend evalua el motivo con un
objeto JSON estructurado antes de crear la cita. La respuesta debe contener
`quality`, `category`, `priority_signals` y `confidence`; el backend valida esos
campos y exige una confianza minima de `0.75`. El LLM no proporciona el motivo ni
ejecuta la cita. Si la evaluacion no es valida, la solicitud permanece pendiente y
se pide una aclaracion. Las señales de prioridad se registran como metadata y no
activan triage clinico automatico en este MVP. Sus descripciones internas usan
lenguaje operativo, no diagnosticos como glaucoma o desprendimiento, y pueden
acompañar la notificacion al doctor despues de una cita creada correctamente. Antes
de usar estas señales con pacientes reales hace falta una politica clinica explicita.

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
- `GOOGLE_CALENDAR_TIMEZONE` tambien define como se resuelven expresiones
  relativas como "hoy" y "mañana" en las consultas del paciente.
- `BUSINESS_WORKDAYS`, `BUSINESS_HOURS_START` y `BUSINESS_HOURS_END` para definir
  los dias y el horario laboral sin modificar codigo.

El adaptador consulta `freeBusy`, sigue las paginas de eventos y lista las citas
creadas por el bot mediante sus propiedades privadas `managed_by=whatsapp_chatbot`
y `patient_id`. Tambien reconoce citas ingresadas manualmente por el medico o
secretaria cuando la descripcion contiene una linea con el numero E.164 exacto:
`WhatsApp: +<E.164>`. Los eventos manuales antiguos deben actualizarse una vez y
las nuevas citas manuales deben conservar ese marcador; sin el no se muestran ni se
pueden modificar desde el bot. El numero se elimina del motivo presentado al agente.
Los listados normales excluyen eventos cancelados; las mutaciones usan
`sendUpdates=all` para evitar la perdida de eventos advertida por Google para
`sendUpdates=none`. Cada cita ocupa 30 minutos y conserva el `PatientScope`
resuelto por el backend.
Los secretos deben vivir fuera del repositorio, por ejemplo en variables de
entorno y archivos montados como secretos.

La funcionalidad `011-doctor-notifications` se implementa por cortes. Una cita
agendada, modificada o cancelada correctamente generara un unico mensaje para cada
doctor configurado. El mensaje incluira el evento, los datos de la cita, el
paciente, los ultimos 10 digitos del telefono, el resumen conversacional y las
señales de prioridad disponibles. El resumen sera contenido obligatorio de esos
tres mensajes y no se enviara de forma independiente.

Las solicitudes para cancelar o reprogramar una cita requieren una confirmacion
explicita del paciente. La primera solicitud no modifica la agenda y muestra la
fecha, el horario y el motivo de la cita sin exponer su ID interno; la operacion se
ejecuta solamente despues de recibir `Si` y expira despues de 10 minutos.

Las solicitudes para crear una cita requieren el nombre del paciente y el motivo
expresado por el paciente. El backend conserva el horario, solicita el nombre en cada
cita nueva, lo guarda o actualiza en `patients.name` y despues pregunta el motivo. La
cita se crea solamente despues de un motivo legible; no usa el motivo
sugerido por el LLM como valor predeterminado. Si el mensaje es evidentemente
ilegible, conserva la solicitud pendiente y pide al paciente que describa nuevamente
el motivo. El texto normalizado del paciente sigue siendo el unico valor guardado
como motivo de la cita.

Si el paciente solicita agendar para un dia sin indicar una hora exacta, el backend
consulta primero los espacios libres de ese dia y los muestra como una lista. La cita
no se crea hasta que el paciente elige un horario.

Si expresa que quiere agendar sin indicar el dia ni una hora exacta, el backend pregunta
la fecha y conserva esa intencion durante 10 minutos. Una respuesta relativa como `hoy`
consulta directamente la disponibilidad usando la zona horaria configurada, sin necesitar
que el LLM reconstruya el contexto.

La configuracion prevista usa `DOCTOR_WHATSAPP_NUMBERS`, una lista de numeros
separados por comas. Todos los doctores configurados reciben una copia del mismo
mensaje. La entrega valida `DOCTOR_NOTIFICATIONS_ENABLED`, recorta espacios,
normaliza numeros E.164 y elimina duplicados. El webhook recolecta los eventos de
agenda confirmados, envia y persiste primero la respuesta del paciente y despues
compone y entrega las notificaciones.

Cuando se usa Google, SQLite conserva la identidad local de cada cita en la tabla
`appointments`. El ID que reciben las herramientas es el `id` interno; el
`google_event_id` queda separado junto con `calendar_id`, paciente, estado, fechas,
motivo y `last_synced_at`. El ID interno se usa para reprogramar o cancelar y no
se muestra al paciente al responder con los detalles de una cita. Google Calendar
sigue siendo la fuente de verdad del estado de la agenda.

El incremento verificado define el modelo de dominio, los contratos tipados de
las cinco herramientas, la validacion previa al proveedor, los errores publicos,
`CalendarProvider`, `FakeCalendarProvider` y `ToolExecutor`. El adaptador
`GoogleCalendarProvider` y su seleccion explicita estan implementados y verificados
con HTTP simulado en el mirror de Raspberry Pi.

El webhook crea el proveedor, recupera el historial desde `ConversationService`,
genera la respuesta, ejecuta herramientas mediante el `ToolExecutor` configurado,
la envia por WhatsApp y registra el resultado. Un fallo de
generacion o envio queda marcado como `failed` para permitir un reintento.
Los fallos de generacion guardan el tipo de excepcion y el codigo HTTP cuando aplica;
el log operativo no registra el texto del paciente ni la respuesta completa del proveedor.

Para depurar, `DEBUG_MODE=true` puede mostrar el nombre del proveedor, el tipo de error y
el codigo HTTP o codigo seguro de agenda, pero solo a los numeros listados en
`DEBUG_WHATSAPP_NUMBERS` (separados por comas). El modo esta apagado por defecto y no
muestra excepciones crudas, prompts, contenido de mensajes, cuerpos HTTP ni credenciales.

Los cortes de eventos, persistencia, composicion, entrega e integracion del webhook
ya estan implementados.
SQLite
crea la tabla `doctor_notifications` con una entrega por
`(event_key, recipient_number)` y conserva estados `pending`, `sending`, `sent` y
`failed`, errores, intentos e IDs devueltos por WhatsApp. El compositor carga el
historial persistido, genera un resumen en una solicitud sin herramientas y
construye un formato fijo sin diagnosticos, transcripciones completas ni IDs
internos. `DoctorNotificationDeliveryService` reutiliza `WhatsAppClient`, intenta
cada destinatario de forma independiente y normaliza los errores antes de
persistirlos. `main.py` conecta el compositor y el entregador al ciclo del webhook;
los errores del doctor se registran sin cambiar la respuesta ya enviada al paciente.
Su alcance, diseno y cortes estan documentados en
`docs/specs/011-doctor-notifications/`.

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
verificacion de Meta. Incluye los flujos completos de cita agendada, modificada y
cancelada, asi como el aislamiento de un fallo de entrega al doctor.

## Endpoints

- `GET /`: comprobacion sencilla del servidor.
- `GET /webhook/whatsapp`: verificacion solicitada por Meta.
- `POST /webhook/whatsapp`: recepcion de eventos enviados por Meta, persistencia
  de mensajes y respuesta generada por el LLM para mensajes de texto. Las
  mutaciones exitosas tambien disparan notificaciones internas al doctor cuando la
  funcionalidad esta habilitada.

Los eventos que no sean mensajes de texto, como estados, imagenes o audios, se
ignoran temporalmente. Las credenciales solo deben existir como variables de
entorno en la Raspberry Pi:

- `WHATSAPP_VERIFY_TOKEN`
- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`

`DATABASE_PATH` no es una credencial, pero debe apuntar a una ruta persistente en
la Raspberry Pi.
