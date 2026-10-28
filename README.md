# WhatsApp Chatbot

Etapa 4: agente LLM basico con un contrato independiente del proveedor,
persistencia conversacional y pruebas sin consumir API mediante un
`FakeLLMProvider`.

## 1. Instalar dependencias

```bash
uv sync
```

### Laboratorio de audio WebRTC

El laboratorio tiene una aplicacion independiente y una base de prueba. Para
instalar las versiones de audio comprobadas, desde la raiz del mirror de la Pi:

```bash
~/.local/bin/uv sync --locked --extra audio
.venv/bin/python scripts/probe_aiortc.py --seconds 10
```

Para abrir el cliente, habilita el laboratorio e inicia su proceso:

```bash
export LAB_CALLS_ENABLED=true
export LAB_AUDIO_MODE=greeting
export LAB_DATABASE_PATH=data/calling-lab.sqlite3
.venv/bin/uvicorn main:create_lab_app --factory --host 127.0.0.1 --port 8001 \
  --no-access-log --no-proxy-headers
```

Desde tu computadora, en otra terminal:

```bash
ssh -N -L 8001:127.0.0.1:8001 asaek@192.168.1.12
```

Abre `http://localhost:8001/lab` y pulsa **Conectar e iniciar llamada**, sin token.
El tono de 440 Hz permite probar sin microfono; tambien puedes seleccionar
microfono, escuchar el saludo y pulsar **Colgar**. El tunel SSH transporta la
senalizacion HTTP; los medios usan conectividad WebRTC directa. Para otro equipo,
empieza en la misma LAN: esa ruta necesita su propia comprobacion.

#### Cliente y red: computadora -> Raspberry

Para preparar este acceso con el agente, usa **`/lab-tunnel`** o pide
**«levanta el tunel de pruebas»**. La skill [lab-tunnel](.agents/skills/lab-tunnel/SKILL.md)
comprueba/inicia el laboratorio de la Pi, reutiliza/abre el forwarding SSH y verifica
el acceso directo desde el Mac. Por defecto usa
Realtime; puedes pedir el saludo sin API. El flujo incluye recuperar el acceso
despues de reiniciar cualquiera de los equipos.

El microfono y los altavoces pertenecen a tu computadora; la Pi recibe y procesa
los frames por red. El cliente y la API se sirven desde el mismo origen, sin
configurar CORS. `http://localhost:8001/lab` mediante SSH es un contexto confiable
para solicitar microfono. `http://192.168.1.12:8001` no lo es: una URL HTTP de
LAN no habilita el microfono por estar en la misma red. HTTPS tambien es valido.

1. Con ambos equipos en la misma LAN, inicia el laboratorio en la Pi y el tunel
   SSH anterior en tu computadora. Mantiene la API en `127.0.0.1:8001` en la Pi.
2. Selecciona **Tono de prueba de 440 Hz** y pulsa **Conectar e iniciar llamada**.
   El mismo boton comprueba HTTP automaticamente y comienza la llamada.
   La senalizacion debe mostrar `HTTP 200; señalización accesible`.
3. En Conectividad
   deben aparecer ICE `connected`/`completed`, conexion `connected`, par host/host
   UDP y contadores RTP de envio/recepcion crecientes. En la sesion de la Pi,
   `non_silent_frames` debe aumentar y el saludo pasar a `completed`.
4. Escucha el saludo en los altavoces de tu computadora. Si llegan paquetes pero
   el audio esta pausado, pulsa Reproducir en el control; revisa volumen y salida
   de audio. La recepcion RTP y la emision `completed` no sustituyen esta escucha.
5. Pulsa **Colgar**, selecciona **Micrófono**, vuelve a conectar, concede permiso
   y habla para activar el saludo. Colgar debe liberar la sesion y permitir otra.

Si HTTP funciona pero ICE falla, revisa VPN, aislamiento de clientes Wi-Fi y
firewalls que bloqueen UDP entre los equipos. Los puertos UDP de medios son
dinamicos: reenviar solo TCP 8001 no los transporta. Esta primera prueba no usa
STUN/TURN. El tunel HTTP de ngrok actual apunta al backend de texto en 8000;
aunque otro tunel sirviera el cliente/senalizacion por HTTPS, no acreditaria audio.
STUN/TURN se evaluara despues de observar una ruta que no conecte directamente.

La API del laboratorio funciona sin token ni cabecera `Authorization`.
El proceso sigue habilitandose explicitamente y escuchando en loopback con acceso SSH:

- `GET /lab/health`: HTTP 200 con `{"status":"ok","mode":"laboratory","audio_mode":"greeting"}`;
  prueba de senalizacion sin asignar recursos de medios.
- `POST /lab/calls`: JSON `{"type":"offer","sdp":"..."}` con candidatos completos.
  Devuelve 201, `session_id`, respuesta SDP y modo `laboratory`.
- `GET /lab/calls/{session_id}`: estado, saludo, metricas y eventos seguros.
- `DELETE /lab/calls/{session_id}`: cierre idempotente y resultado de liberacion.

Solo se admite una sesion activa. Los limites predeterminados son 20 s para
negociar, 60 s sin audio entrante y 600 s de duracion maxima. `main:app` no
publica estas rutas. El saludo fijo esta en `assets/lab-greeting.wav`.
Si SQLite no permite finalizar, el audio se cierra igualmente y la API devuelve
503: pulsa **Colgar** otra vez para persistir el resultado cuando se recupere.

Verificacion automatizada en la Pi:

```bash
~/.local/bin/uv run --locked --extra audio python -m unittest discover -s tests -v
~/.local/bin/uv run --no-project --with playwright==1.56.0 --with httpx \
  python scripts/verify_lab_browser.py
```

El segundo comando utiliza `/usr/bin/chromium` y crea/cierra su propio backend,
puerto y base temporal. Comprueba reproduccion y cierres desde el cliente
real. Las [medidas y fronteras verificadas](docs/verification/2026-10-18-aiortc-audio-laboratory.md)
incluyen Opus, CPU y memoria. La [verificacion LAN](docs/verification/2026-10-18-webrtc-client-lan.md)
acredita tambien Chrome en la computadora contra la Pi, con UDP directo sin
STUN/TURN. La escucha fisica y el microfono real quedan como comprobacion manual.

### Conversacion de voz nativa con OpenAI Realtime

El modo `realtime` recibe audio directamente del navegador, lo envia desde la Pi
a OpenAI por WebSocket y reproduce la voz generada. La transcripcion se guarda
en paralelo; el agente de texto no se ejecuta por cada intervencion.

Desde la raiz del mirror de la Pi, instala ambos extras y usa el tunel SSH
descrito arriba:

```bash
~/.local/bin/uv sync --locked --extra audio --extra voice
export LAB_CALLS_ENABLED=true LAB_AUDIO_MODE=realtime
.venv/bin/uvicorn main:create_lab_app --factory --host 127.0.0.1 --port 8001 \
  --no-access-log --no-proxy-headers
```

Se requiere `OPENAI_REALTIME_API_KEY` o `OPENAI_API_KEY` en la configuracion secreta.
El modelo de texto y sus credenciales genericas no se usan para voz. Las opciones
de `.env.example` incluyen `VOICE_MODEL=gpt-realtime-2.1`, `VOICE_VOICE=marin` y
`VOICE_TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe`. La transcripcion puede tener
cargo separado. La sesion inicial dura hasta 300 s (5 minutos), espera hasta 30 s de verdadera
inactividad. `VOICE_MAX_SESSIONS` limita a cinco sesiones por perfil por defecto y
acepta `unlimited` para pruebas controladas. Es una cuota de sesiones, no un limite
monetario de OpenAI; la cuota diaria queda pendiente antes de uso operativo.

En `http://localhost:8001/lab`, deja **Micrófono** y pulsa **Conectar e iniciar llamada**.
Cada llamada comienza con un saludo generado con contexto vacio y herramientas
deshabilitadas. El historial reciente de voz/texto se prepara al conectar y sigue
disponible para atender tu intervencion. Puedes interrumpir el saludo hablando
o escribiendo: se cancela y se atiende tu turno, sin reiniciarlo despues. La ventana
actual conserva 12 mensajes. El agente puede consultar antecedentes mas antiguos
con `search_conversation_history`, por palabras del tema, fechas inclusivas y canal.
Recibe hasta seis fragmentos de 600 caracteres del mismo perfil, con procedencia
y fecha de inicio de sesion identificada como tal. Consultar no retoma gestiones,
modifica propuestas ni renueva autorizaciones. El contexto reciente enriquecido
con resultados de acciones sigue pendiente.
Tambien puedes elegir **Muestra de voz (archivo)**: acepta hasta 30 s/2 MB y envia
la muestra despues del saludo del modelo. `assets/voice-availability-sample.wav`
pregunta por disponibilidad de mañana y permite probar una herramienta sin microfono.
El tono de 440 Hz sirve a la prueba de transporte, no como intervencion hablada.

El backend fija `VOICE_LAB_PROFILE` e identidad de prueba. Consulta una agenda
falsa; crear, mover y cancelar preparan una propuesta, leen su pregunta y requieren
una decision en un turno posterior. El backend verifica emision completa, datos,
vigencia, generacion y reclamacion durable. Una correccion o cierre anterior a la
reclamacion impide ejecutar; una operacion ya reclamada conserva su resultado.
La pregunta formula primero la hora de inicio en formato de 12 horas con AM/PM y
despues la fecha `DD/MM/YYYY`, por ejemplo: `a las 10:00 AM del 19/10/2026`.

Si respondes antes de que termine la pregunta de confirmacion, el bot conserva
nombre, motivo y horario y vuelve a preguntar tras revisar la disponibilidad.
La respuesta anticipada no reserva: confirma otra vez cuando termine la pregunta
nueva. Esa interrupcion no debe exigir repetir tus datos ni anunciar sesion perdida.
Si VAD divide la afirmacion en turnos intermedios y cancela una respuesta, el backend
espera hasta un segundo la transcripcion del turno vigente. Solo una afirmacion clara
de ese turno puede confirmar la misma propuesta, si la pregunta se emitio completa;
si falta o es ambigua, vuelve a preguntar sin modificar la cita.

El panel **Mensajes del mismo paciente ficticio** permite escribir durante la
llamada o despues de colgar. Comparte identidad, historial y agenda con la voz.
Durante una llamada usa su conexion Realtime; sin llamada mantiene una sesion de
texto acotada por los mismos plazos y cuota de conexiones. No usa el numero ni
los pacientes operativos de WhatsApp. Para continuar una propuesta en otro canal,
escribe **Retomemos la cita** y responde a la pregunta nueva: un `si` escrito no
confirma la pregunta de voz. Una gestion nueva reemplaza la anterior.

`POST /lab/messages` recibe `{"message_id":"id-unico","text":"..."}` con el
acceso directo sin token. Hasta 2000 caracteres; no acepta identidad/canal del cliente.
Reintentar el mismo ID/cuerpo devuelve la misma respuesta, incluso tras un fallo
de escritura; otro cuerpo con el mismo ID se rechaza. `GET /lab/history` devuelve
el historial del perfil fijo, con `channel`, `generation_state`, `state`,
`generated_ms` y `emitted_ms`. Publicar texto de laboratorio no significa enviar
un mensaje de WhatsApp. Una pregunta textual solo se habilita para confirmar
despues de publicar el cuerpo HTTP completo.
Ver [controles y continuidad del paciente ficticio](docs/verification/2026-10-19-voice-text-controls.md).

`VOICE_DATABASE_PATH` es una SQLite exclusiva, diferente de llamadas y pacientes.
Si se omite se deriva del nombre de `LAB_DATABASE_PATH` con sufijo `-voice`.
Conserva perfil, transcripciones, estados de emision, propuestas, resultados y
agenda falsa entre sesiones. `VOICE_CALENDAR_PROVIDER=fake` mantiene esa agenda
simulada y es el valor por defecto. `VOICE_CALENDAR_PROVIDER=google` conecta la
pagina HTML Realtime a los calendarios de `GOOGLE_CALENDAR_IDS`, usando las
credenciales y zona horaria existentes. Las reservas confirmadas en este modo son
eventos reales; el cliente y `/lab/health` muestran el proveedor activo.
Los eventos de voz usan `managed_by=whatsapp_voice_lab`, de modo que el backend
operativo de WhatsApp no los presenta ni modifica como citas de pacientes. La
identidad del laboratorio sigue siendo ficticia; las reservas simuladas existentes
no se migran a Google automaticamente. Las transcripciones ausentes dejan marcadores;
las tardias completan historial sin ejecutar acciones. El audio permanece temporal.
`metrics.voice_usage` registra por modelo tokens de audio/texto/cache y transcripcion.
El panel **Rendimiento y consumo** muestra `metrics.voice_performance` y
`metrics.voice_cost`: primer PCM recibido/primer frame emitido, tiempo de corte
local y herramientas, CPU, pico RSS y colas. La referencia del backend es el evento
VAD recibido (commit si falta), por lo que no incluye el VAD/red anteriores.
Emision en la Pi y reproduccion en el Mac son medidas distintas. Con un archivo,
`sample_end_to_browser_playback_signal_ms` mide aproximadamente fin de muestra ->
primera señal remota en el renderizador, con muestreo de 20 ms; no mide el altavoz.
Las metas sin herramientas son p50 <= 1500 ms / p95 <= 3000 ms end-to-end. Los
percentiles de backend son por sesion e incluyen numero de muestras; no demuestran
por si solos esas metas. El saludo y los turnos con herramientas se separan.

El costo en USD es estimado, con tarifas/fuente/fecha del 20 de octubre para
`gpt-realtime-2.1` y `gpt-4o-mini-transcribe`; incluye la transcripcion separada y
el descuento de cache. Si configuras otro modelo o faltan detalles/eventos finales,
el total es `null`, con `complete=false` y un subtotal conocido; no significa costo
cero. Revisa el consumo tambien en OpenAI antes de ampliar los cinco intentos.
La transferencia entre chat operativo y voz corresponde al corte C4; la conexion
con Meta Calling corresponde a C5.

El laboratorio limita las sesiones durables por perfil mediante
`VOICE_MAX_SESSIONS` (5 por defecto). `unlimited` desactiva la cuota total de sesiones
para pruebas controladas; no existe aun una cuota diaria. En la Pi de pruebas esta
configurado explicitamente `unlimited`. Si se establece un maximo numerico y se
alcanza, iniciar una sesion devuelve HTTP 429 con el conteo; reiniciar no restablece
la cuota.

Verificacion sin APIs y pruebas de pago separadas, siempre en la Pi:

```bash
.venv/bin/python -m unittest discover -s tests -v
# UI, canales y reintentos con WebRTC real/proveedor falso, sin costo de API:
~/.local/bin/uv run --no-project --with playwright==1.56.0 --with httpx \
  python scripts/verify_lab_controls.py
# OpenAI real, WebRTC real y muestra conocida; una sesion de pago acotada:
.venv/bin/python scripts/probe_realtime_voice.py
# Navegador real, OpenAI, consulta de agenda falsa y continuidad voz/texto:
~/.local/bin/uv run --no-project --with playwright==1.56.0 --with httpx \
  python scripts/verify_realtime_browser.py
```

Los scripts de pago usan bases y cuotas temporales: invocaciones separadas no
comparten el contador de sesiones. Cada ejecucion informa su consumo; el
presupuesto de referencia aprobado para las pruebas iniciales es 5 USD.
El verificador de navegador admite `--cdp-url`, `--port` y `--expected-peer` para
Chrome en otra computadora. La prueba automatizada silencia la reproduccion y
usa muestras sinteticas; la escucha y el microfono fisicos se comprueban manualmente.
Ver [evidencia de voz nativa](docs/verification/2026-10-19-native-realtime-voice.md).
El [resultado del hito y mediciones](docs/verification/2026-10-20-realtime-milestone.md)
registra la verificacion mas reciente: 453 tests en la Pi, navegador Mac/Pi/OpenAI,
costos estimados y las comprobaciones humanas que siguen pendientes.

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
de enviarse. Las listas de disponibilidad para agendar o reprogramar muestran solo
la hora de inicio en formato de 12 horas con AM/PM, por ejemplo `- 9:30 AM`,
`- 12:00 PM` y `- 1:00 PM`, tambien al retomar una gestion pausada. Las listas y
detalles de citas reservadas y las confirmaciones de cancelacion o reprogramacion
tambien muestran solo el inicio, por ejemplo `Horario: 9:00 AM` o `Hora: 9:00 AM`.
Se usa la zona horaria de la agenda y el paciente puede seleccionar un horario
indicando AM o PM.

Despues de agendar, reprogramar o cancelar correctamente, el paciente recibe una
`CONFIRMACION DE CITA` con tipo de evento, los bloques `CITA` (fecha, inicio con
AM/PM, motivo y estado definitivo) y `PACIENTE` (nombre completo y ultimos 10
digitos del telefono). El renderizado de estos bloques se comparte con la
notificacion del doctor en `appointment_messages.py`. El resumen y las señales de
prioridad siguen en el mensaje interno. La confirmacion no requiere otro llamado
al LLM y funciona con notificaciones al doctor deshabilitadas.

Cuando `LLM_REASON_EVALUATION_ENABLED=true`, el backend evalua el motivo con un
objeto JSON estructurado antes de crear la cita. La respuesta debe contener
`quality`, `category`, `priority_signals`, `priority_signal_evidence` y `confidence`; el backend valida esos
campos y exige una confianza minima de `0.75` para aceptar la clasificacion del LLM.
Un motivo general comprensible, como `Tengo problemas en el ojo izquierdo`, basta:
no se exige diagnostico, intensidad ni duracion. Un respaldo local acotado permite
aceptar esas expresiones cuando el evaluador pide mas detalle, tiene baja confianza
o falla. El LLM no proporciona el motivo ni ejecuta la cita. Sin respaldo suficiente,
la solicitud permanece pendiente: el bot distingue fallo tecnico, incertidumbre de
la evaluacion y falta de motivo, reconociendo el texto recibido y usando preguntas
mas concretas en los siguientes intentos. Las señales de prioridad se registran como metadata y no
activan triage clinico automatico en este MVP. Sus descripciones internas usan
lenguaje operativo, no diagnosticos como glaucoma o desprendimiento, y pueden
acompañar la notificacion al doctor despues de una cita creada correctamente. Antes
de usar estas señales con pacientes reales hace falta una politica clinica explicita.

En cada cita nueva se solicita el nombre completo antes del motivo. El backend
conserva todas sus partes y normaliza solo espacios. Si una parte contiene señales
claras de texto de prueba, pregunta por su escritura citando el nombre completo,
por ejemplo: `¿Me confirmas tus apellidos? Recibí ‘Asael Ponce jhbashkda’.`
El paciente puede responder `sí` para confirmar un apellido poco comun o escribir
su nombre completo corregido. Hasta entonces se conserva el horario y el nombre
recibido como pendiente, sin reemplazar el nombre registrado. Al aceptarlo, el bot
muestra el nombre completo que guardo antes de pedir el motivo.
Una seleccion como `quisiera una cita a las 9 am` continua la lista ofrecida sin
reiniciar la reserva. El nombre aceptado se conserva para esa solicitud, incluso
tras reinicios. Respuestas conversacionales reconocibles como `ya te lo habia dich`,
negativas a dar el nombre o `Tengo los ojos rojos` no se guardan como nombres:
se conserva el horario y se pide aclarar el dato pendiente.
Las selecciones admiten separadores accidentales entre palabras, como
`QUisiera.a las 10 am`, y cierres como `a las 10 am está bien`. Una hora reconocida
fuera de los horarios ofrecidos recibe una respuesta de no disponibilidad; una
hora ambigua pide AM/PM y un texto sin hora valida pide aclaracion.

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

Una solicitud directa como `quisiera cancelar la de las 10 am` se resuelve en
agenda y guarda su accion antes de preguntar. El primer `si por favor` cancela
esa cita; una referencia ambigua o no coincidente pide precisar dia y horario.
Una pregunta textual del modelo sin accion guardada no cuenta como confirmacion.

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

Preguntas informativas o saludos durante una gestion de cita pausan su avance.
`Retomemos la cita` recupera el paso pendiente, incluido el nombre ya recibido para
esa reserva; una fecha o seleccion clara tambien puede retomarlo. La pausa se
conserva en SQLite y sobrevive a reinicios y al recorte del historial del modelo.
Los horarios vencidos se consultan de nuevo. Una cancelacion o reprogramacion
pausada requiere una confirmacion nueva; un `Si` durante otro tema no la ejecuta.
`Ya no quiero agendar`, `No la modifiques` o `No quiero cancelarla` abandonan la
operacion sin alterar la cita. Una nueva gestion explicita reemplaza la anterior.

Al elegir el nuevo horario de una cita, puedes responder `quisiera cambiarla a las
12 pm`, `me gustaría moverla a las 12 pm`, `ponla a las 12 pm`, `me viene bien a las
12 pm` o `¿podrías cambiarla a las 12 pm?`. Tambien se reconoce `al mediodía`.
El bot conserva la cita original y pide confirmar el cambio. Si recibio `12 p,`,
pregunta por la hora completa con AM o PM; responder `12 pm` continua la gestion.

La configuracion prevista usa `DOCTOR_WHATSAPP_NUMBERS`, una lista de numeros
separados por comas. Todos los doctores configurados reciben una copia del mismo
mensaje. La entrega valida `DOCTOR_NOTIFICATIONS_ENABLED`, recorta espacios,
normaliza numeros E.164 y elimina duplicados. El webhook recolecta los eventos de
agenda confirmados, envia y persiste primero la respuesta del paciente y despues
compone y entrega las notificaciones.

La configuracion de entrega al doctor agrega:

```dotenv
DOCTOR_NOTIFICATION_TRANSPORT=template
DOCTOR_WHATSAPP_TEMPLATE_NAME=aviso_cita_medico
DOCTOR_WHATSAPP_TEMPLATE_LANGUAGE=es_MX
DOCTOR_WHATSAPP_TEMPLATE_COMPONENTS='[{"type":"body","parameters":[{"type":"text","text":"{event_type}"},{"type":"text","text":"{date}"},{"type":"text","text":"{time}"},{"type":"text","text":"{reason}"},{"type":"text","text":"{status}"},{"type":"text","text":"{patient_name}"},{"type":"text","text":"{patient_phone}"},{"type":"text","text":"{summary}"},{"type":"text","text":"{priority_signals}"}]}]'
```

La bandera de avisos habilita su captura, independientemente de la disponibilidad
del transporte. Con `template` y datos vacios, el aviso queda `pending` con el
motivo `Configuración de plantilla incompleta.`, sin reclamar un intento de envio
ni invocar el resumidor. La cita y su confirmacion al paciente siguen su curso.
Un transporte desconocido o datos mal formados tambien retienen el aviso con un
motivo estable. Nombre e idioma se recortan y validan por formato; esta validacion
no acredita aprobacion por Meta. `WhatsAppClient.send_template()` implementa el
envio mediante la misma Cloud API. Al completar nombre e idioma tambien se requiere
un mapeo explicito en `DOCTOR_WHATSAPP_TEMPLATE_COMPONENTS`; vacio conserva el aviso
con `Mapeo de plantilla pendiente.`. La plantilla `aviso_cita_medico` en `es_MX`
fue reportada como aprobada por el usuario y se configuro con nueve parametros
posicionales de cuerpo. Su encabezado fijo se renderiza en Meta. El contrato y
texto exactos estan en
[`approved-template.md`](docs/specs/011-doctor-notifications/approved-template.md).
La prueba de entrega real requiere credenciales vigentes.

El 25/10/2026 se confirmo `APPROVED` para el emisor configurado y una prueba al
doctor obtuvo el callback real `delivered`, sin modificar la agenda. Ver
[la evidencia de entrega](docs/verification/2026-10-25-approved-template-delivered.md).

La plantilla debe pertenecer a la cuenta de WhatsApp Business del emisor indicado
por `WHATSAPP_PHONE_NUMBER_ID`; que el token autentique no garantiza que esa
cuenta tenga la plantilla. La configuracion y comprobaciones de activacion estan
en [la verificacion de la plantilla aprobada](docs/verification/2026-10-25-approved-template-delivered.md).

El mapeo es un arreglo JSON de componentes de texto (`header`, `body` y botones
`url`), conservando el orden y los nombres `parameter_name` cuando la plantilla
los requiera. Cada parametro usa `text` con referencias a `event_type`, `status`,
`date`, `time`, `reason`, `patient_name`, `patient_phone`, `summary` y
`priority_signals`. Se pueden agrupar varios datos en una variable, sin fijar su
cantidad. `notification_body` representa el aviso completo como alternativa. El
mapeo debe conservar todos los datos del aviso; referencias desconocidas o un
mapeo incompleto retienen el evento. El texto de los parametros se compacta para
evitar saltos y tabuladores, conservando el cuerpo original en SQLite.

Ejemplo **ficticio**, no configurado como plantilla real:

```json
[
  {"type":"header","parameters":[{"type":"text","text":"{event_type}: {status}"}]},
  {"type":"body","parameters":[
    {"type":"text","parameter_name":"cita","text":"{date} {time}; {reason}"},
    {"type":"text","parameter_name":"paciente","text":"{patient_name}: {patient_phone}"},
    {"type":"text","parameter_name":"resumen","text":"{summary} {priority_signals}"}
  ]}
]
```

La estructura real debe copiar los componentes, el orden y los nombres que Meta
apruebe. Los datos estructurados se guardan junto al cuerpo y, al reclamar el primer
envio, se congela nombre, idioma y componentes por entrega. Los reintentos conocidos
reutilizan ese contenido incluso tras reiniciar; una respuesta perdida o sin ID
queda incierta y no causa otro envio automatico.

Si la variable de transporte no existe se conserva `text`, por compatibilidad;
`.env.example` selecciona `template` explicitamente. Los destinatarios siguen
resolviendose exclusivamente desde `DOCTOR_WHATSAPP_NUMBERS`. Chat conserva el
snapshot del evento y deja su notificacion sin completar en `reply_outbox`; un
webhook repetido puede retomarla sin repetir la cita ni la respuesta del paciente.
El laboratorio conserva el evento y lo recupera mediante su ciclo existente.
Chat y laboratorio recuperan sus avisos al arrancar y cada 60 s mediante el mismo
ciclo de recuperacion. El chat puede hacerlo sin otro mensaje del paciente y
recupera tambien la interrupcion entre confirmar al paciente y capturar el aviso.
Se usan solamente eventos persistidos; la recuperacion no llama herramientas de agenda.

Cada entrega conserva evento, contexto acotado, contenido y datos de plantilla.
Los intentos quedan en `doctor_notification_attempts`, con cuerpo, payload,
revision local de plantilla, fechas y resultado. La revision local identifica la
configuracion utilizada, no inventa una revision interna de Meta.

- Fallos de conexion previos al despacho, HTTP 429/5xx y errores transitorios de
  Meta: espera persistida de 60, 120, 240 segundos, etc., hasta 3600 s. Se respeta
  `Retry-After` cuando exige mas espera, hasta 24 horas.
- Rechazos de autenticacion/configuracion: quedan detenidos hasta detectar una
  correccion de los datos relevantes o credenciales. Los errores de composicion
  tambien tienen espera y no incrementan los intentos de envio.
- Respuesta perdida o sin ID, tanto en texto como plantilla: estado `sending`
  incierto, sin vencimiento que autorice otro envio.

Las correcciones se sincronizan y cargan mediante la recarga habitual del backend
y laboratorio. Una entrega ya registrada mantiene sus destinatarios; agregar otro
doctor solo afecta eventos nuevos. Un destinatario retirado queda detenido mientras
no este configurado. Los reintentos transitorios usan el payload original. Si Meta
rechazo definitivamente una configuracion y esta se corrige, el siguiente intento
puede usar la configuracion corregida, conservando la anterior en su auditoria.

Para conciliar un envio incierto, comprueba primero que el intento termino y
obtiene evidencia externa. Si el proceso se interrumpio, verifica que ya no siga
despachando. Sustituye `ID` y `N` en el comando ejecutado desde la raiz de Raspberry:

```sh
.venv/bin/python scripts/reconcile_doctor_notification.py \
  --database data/chatbot.sqlite3 --notification-id ID --attempt N \
  --outcome accepted --provider-message-id wamid.RECUPERADO \
  --reason "Referencia tecnica de la comprobacion"
```

`accepted` exige el ID recuperado de Meta y evita otro envio; `not_delivered`
habilita un nuevo intento solo con ausencia de entrega comprobada. La utilidad
guarda la referencia y rechaza un numero de intento obsoleto. `configuration_fixed`
permite liberar un bloqueo tras una correccion externa que no cambio las variables
(por ejemplo, aprobacion en Meta). Para laboratorio se usa
`data/calling-lab-voice.sqlite3`. La utilidad concilia, pero no envia mensajes.

Para verificar dos conversaciones distintas, usa un WhatsApp de paciente diferente
de los numeros de `DOCTOR_WHATSAPP_NUMBERS`. Si pruebas como paciente desde el mismo
numero del doctor, la `CONFIRMACION DE CITA` y la `NOTIFICACION INTERNA DE CITA`
son mensajes separados dirigidos a la misma cuenta y aparecen en un solo chat.
El resumen y las señales de prioridad pertenecen al aviso interno. La
[auditoria de destinatarios](docs/verification/2026-10-22-doctor-notification-routing.md)
contrasta los registros y la configuracion efectiva de Raspberry.

El chat y voz/texto de `/lab` usan `DoctorNotificationTrigger`: comparten formato,
resumen, señales de prioridad, destinatarios y envio. En laboratorio, el evento
se guarda junto al resultado de la cita y se procesa fuera del audio; los avisos
pendientes se recuperan al arrancar y cada 60 segundos, sin repetir la agenda.
Los reintentos conservan el cuerpo preparado. Una propuesta, un rechazo o un fallo
de agenda no notifica. Las acciones antiguas sin evento persistido no se reejecutan
ni notifican retroactivamente. El perfil ficticio muestra `Telefono: No informado`.
`DOCTOR_NOTIFICATIONS_ENABLED=true` habilita tambien estos envios: con agenda fake
los datos son simulados, pero el destinatario y el envio WhatsApp son los configurados.
La entrega efectiva requiere un token de Meta vigente. En modo `text` el envio es
texto libre: Meta exige que el doctor le haya escrito al numero del bot dentro de las
ultimas 24 horas. Fuera de esa ventana se necesita una plantilla aprobada por Meta;
el adaptador y el mapeo de `aviso_cita_medico` estan configurados y una prueba real
obtuvo `delivered` el 25/10/2026. Un HTTP 200 con ID de mensaje confirma
aceptacion inicial, pero Meta puede rechazar la entrega despues con `131047`.
El control interno `status=sent` conserva el significado de aceptacion inicial;
la entrega real se consulta en `delivery_status`, no se deduce de HTTP 200. Ver el
[diagnostico de entrega](docs/verification/2026-10-22-whatsapp-doctor-delivery-window.md).

El webhook persiste los estados de Meta en `whatsapp_delivery_receipts` dentro de
la base operativa de chat. El historial conserva ID, destinatario normalizado,
estado, timestamp y codigos numericos de error, sin guardar cuerpos de error crudos.
La proyeccion actualiza tanto avisos de chat como de voz por ID de Meta **y**
destinatario. No usa el telefono por si solo ni ejecuta conversacion o envios.

| `delivery_status` | Significado |
| --- | --- |
| `accepted` | La API devolvio un identificador; todavia no confirma envio al destinatario |
| `sent` | Meta informa que envio el mensaje |
| `delivered` | Meta informa que llego al destinatario |
| `read` | Meta informa lectura |
| `failed` | Meta informa fallo de entrega |

`api_accepted_at` conserva la aceptacion aunque despues falle; `delivery_status_at`
conserva la fecha del estado de Meta. La auditoria de cada intento mantiene su
propio estado. Los callbacks tardios de un intento antiguo no cambian el intento
actual. Los avisos historicos con ID se migran como `accepted`, sin inventar entrega.

Primero se confirma el almacenamiento del callback y despues se proyecta en
segundo plano. Un ciclo al arrancar y cada 5 s retoma los que llegaron antes de
guardar el ID o mientras la base de voz estaba indisponible. Duplicados exactos no
crean otra entrada; un estado atrasado no revierte lectura o entrega. `failed`
prevalece sobre `sent`, pero no sobre evidencia de `delivered`/`read`. El historial
completo se conserva incluso ante estados contradictorios. Un callback nuevo que
llegue durante otra proyeccion conserva su propio estado pendiente.

Un fallo asincrono del intento actual alimenta la espera o bloqueo de configuracion
existentes, sin programar el mismo fallo dos veces. La aceptacion de otro intento
no reinicia la espera exponencial; la entrega/lectura confirmada si la reinicia y
cancela el reintento pendiente. La conciliacion de una respuesta perdida puede
recuperar el ID y permitir correlacionar callbacks ya guardados. Si no se consigue
persistir un callback valido, el webhook devuelve 503 para que Meta lo repita.

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
prepara su cuerpo y eventos de cita en SQLite antes de enviarla por WhatsApp y
registra el resultado. Un fallo confirmado de envio permite reintentar ese mismo
texto sin volver a generar ni ejecutar herramientas. Si ya hay turnos posteriores
procesados, el mensaje antiguo se reconoce con HTTP 200 y se descarta sin enviar
ni reabrir la gestion. Los turnos del mismo paciente se serializan en el runtime
Uvicorn de un proceso; pacientes distintos pueden avanzar en paralelo.
`reply_delivery_attempts` conserva fechas y resultado de cada intento, mientras
`messages.created_at` conserva la fecha original del registro. Un procesamiento
interrumpido o un envio con resultado incierto no se repite automaticamente.
El detalle esta en `docs/specs/018-safe-webhook-retries/`.
Los fallos de generacion guardan el tipo de excepcion y el codigo HTTP cuando aplica;
el log operativo no registra el texto del paciente ni la respuesta completa del proveedor.

Para depurar, `DEBUG_MODE=true` puede mostrar el nombre del proveedor, el tipo de error y
el codigo HTTP o codigo seguro de agenda, pero solo a los numeros listados en
`DEBUG_WHATSAPP_NUMBERS` (separados por comas). Cada numero configurado debe incluir
explicitamente el prefijo `+` y cumplir el formato E.164, por ejemplo
`DEBUG_WHATSAPP_NUMBERS=+521234567890`; omitir `+` no autoriza al remitente. El modo
esta apagado por defecto y no muestra excepciones crudas, prompts, contenido de mensajes,
cuerpos HTTP ni credenciales.

Los cortes de eventos, persistencia, composicion, entrega e integracion del webhook
ya estan implementados.
SQLite
crea la tabla `doctor_notifications` con una entrega por
`(event_key, recipient_number)` y conserva estados `pending`, `sending`, `sent` y
`failed`, errores, intentos e IDs devueltos por WhatsApp. El compositor carga el
historial persistido, genera un resumen en una solicitud sin herramientas y
construye un formato fijo sin diagnosticos, transcripciones completas ni IDs
internos. Analiza semanticamente el motivo y los mensajes del paciente de la gestion
actual, con evidencia literal para las señales interpretadas por el LLM; no exige
que una interpretacion coincida ademas con palabras clave. Las reglas locales
aportan un respaldo, incluido `ocular_discharge` para secrecion amarillenta, verdosa
o abundante y variantes como `laga;as`. El historial se separa de citas anteriores
mediante eventos persistidos y respuestas de exito del backend; se excluyen mensajes
posteriores al evento y sintomas sugeridos por el asistente. Pocas lagañas al
despertar o sintomas negados no fuerzan una señal.
`DoctorNotificationDeliveryService` reutiliza `WhatsAppClient`, intenta
cada destinatario de forma independiente y normaliza los errores antes de
persistirlos. `main.py` conecta el disparador compartido al webhook y al laboratorio;
los errores del doctor se registran sin cambiar la respuesta ya enviada al paciente.
Su alcance, diseno y cortes estan documentados en
`docs/specs/011-doctor-notifications/`.

## 3. Iniciar el servidor

```bash
uv run uvicorn main:app --reload
```

El backend queda disponible en <http://127.0.0.1:8000>.

### Sincronizar y recargar la Raspberry Pi

La solicitud `local to raspberry` sigue la skill del proyecto en
`.agents/skills/local-to-raspberry/SKILL.md`: sincroniza, reinicia el backend y
verifica el health check y los webhooks local y publico. Incluye por defecto la
copia completa del `.env` local a la Pi, con igualdad byte por byte y modo `600`,
sin mostrar credenciales ni pedir otra confirmacion. Una solicitud explicita sin
`.env` lo conserva; una solicitud de una sola variable actualiza solo esa clave.
El reinicio y la verificacion forman parte del flujo aunque no haya codigo nuevo.
Uvicorn en la Pi corre sin `--reload`, por lo que copiar archivos por si solo no
carga cambios en el proceso. El flujo termina cuando se confirma el reinicio y
las rutas responden correctamente y, si estan configuradas, las credenciales de
envio de WhatsApp pasan una consulta autenticada de solo lectura a Meta.

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
Si la respuesta fallo, recupera el cuerpo preparado solamente cuando el turno
sigue vigente y el error permite reintentar con resultado conocido.

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
