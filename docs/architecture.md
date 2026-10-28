# Arquitectura

## Estado

Arquitectura evolutiva. El contrato de herramientas de citas, el orquestador del
agente y el adaptador de Google Calendar estan verificados con dobles HTTP; una
cuenta real requiere credenciales fuera del repositorio.

## Arquitectura actual

```text
WhatsApp
    |
    v
WhatsApp Cloud API
    |
    v
ngrok
    |
    v
FastAPI + Uvicorn
    |
    v
FastAPI procesa mensajes de texto y callbacks de entrega
    |
    v
Conversation Service
    |
    +-- Repositories -> SQLite
    +-- LLMProvider -> OpenAICompatibleLLMProvider
    +-- AgentOrchestrator -> ToolExecutor -> CalendarProvider (fake o Google)
    |
    v
WhatsAppClient -> WhatsApp Cloud API
```

Para pruebas automatizadas, las dependencias externas se sustituyen por
`FakeLLMProvider`, `FakeWhatsAppClient` y una base SQLite temporal. El webhook se
ejecuta mediante `TestClient` sin consumir APIs.

Durante el desarrollo local, ngrok proporcionara la URL publica que Meta
necesita para comunicarse con FastAPI.

## Espejo de ejecucion en Raspberry Pi

`specs/017-local-to-raspberry/` define el despliegue operativo del MVP. La skill
sincroniza proyecto y `.env` completo desde el checkout local, comprueba igualdad
en memoria y modo `600`, y recarga el backend verificado desde la raiz del mirror.
La copia masiva trata el codigo; un paso dedicado transfiere `.env` sobre SSH con
reemplazo completo y permisos restringidos. Los secretos quedan fuera de Git y
del reporte. La configuracion efectiva del proceso debe coincidir con la copiada.
Las verificaciones incluyen rutas locales/publicas y autenticacion de Meta de
solo lectura, para distinguir un webhook saludable de una credencial de envio valida.

## Laboratorio de audio implementado (021, A-E)

```text
Navegador de laboratorio <--- HTTP oferta/respuesta + ICE completo ---> main:create_lab_app
           |                                                               |
           +------------------- WebRTC / Opus ----------------> AiortcCallMedia
                                                                           |
                                           CallingService (lifespan, plazos, cierre)
                                                                           |
                                            CallingRepository -> SQLite de laboratorio
```

La factory crea otra aplicacion y proceso, habilitado explicitamente, sin token
de acceso y con base exclusiva; escucha en loopback y se accede mediante SSH.
`main:app` no publica `/lab` ni `/lab/calls`. Una llamada global por base/proceso,
cierre idempotente y tareas supervisadas. El saludo WAV se emite al detectar senal
de entrada; sus estados y metricas se conservan sin SDP ni audio recibido.
La agenda operativa se compone en el lifespan de texto, evitando efectos al
importar la factory. `aiortc`/PyAV se importan solo al arrancar el laboratorio,
mediante el extra opcional `audio` (ADR 0055).

El boton **Conectar e iniciar llamada** comprueba HTTP con `GET /lab/health`
automaticamente antes de reservar una sesion, sin campo ni cabecera de token, y
observa ICE, par host/protocolo, contadores RTP y reproduccion por separado. Para
usar microfono desde la computadora se sirve en localhost mediante SSH (o HTTPS);
HTTP en una IP LAN no basta. El tunel transporta senalizacion, mientras los medios
usan candidatos host y UDP directo. No se han incorporado STUN/TURN; se evaluaran
segun la conectividad observada. El ngrok del webhook apunta al backend de texto.

Se comprobaron tonos bidireccionales y reproduccion Chromium/backend en la misma
Raspberry, candidatos host y Opus. La [verificacion](./verification/2026-10-18-aiortc-audio-laboratory.md)
incluye CPU, memoria, desconexion y apagado. Tambien se comprobo
[Chrome en la computadora y backend Pi por LAN](./verification/2026-10-18-webrtc-client-lan.md),
con medios UDP directos sin STUN/TURN. Escucha fisica, microfono real y
conectividad fuera de esa frontera siguen pendientes.

## Diseno propuesto: integracion de llamadas entrantes (021)

### Arquitectura aprobada de voz nativa (ADR 0056)

```text
Navegador / futuro Meta <-- WebRTC/Opus --> AiortcCallMedia
                                               |
                                          VoiceSession
                                               |
                                    OpenAI Realtime (WebSocket PCM24k)
                                               |
                            VoiceTools -> validadores/ToolExecutor -> fake | Google
                                               |
                                VoiceRepository (SQLite de voz exclusiva)
```

El modelo recibe audio y genera audio. El agente de texto no participa en cada
intervencion. Las instrucciones comunes y la ejecucion validada de herramientas
se reutilizan; el historial se transcribe en paralelo. Una transcripcion tardia
no ejecuta acciones. Se distinguen generacion, emision, interrupcion y entrega
escrita. Las confirmaciones de laboratorio verifican pregunta literal emitida y
decision de un turno posterior. Su fecha y hora se presentan en español de México,
primero la hora de inicio en 12 horas con AM/PM y despues la fecha `DD/MM/YYYY`.
La [verificacion del formato](./verification/2026-10-21-voice-mexican-date-format.md)
registra la regresion y la recarga del laboratorio. La continuidad con chat operativo
sigue en C4.

`laboratory_executor()` selecciona `FakeCalendarProvider` por defecto o el
`GoogleCalendarProvider` cuando `VOICE_CALENDAR_PROVIDER=google`. En Google, el
propietario de evento `whatsapp_voice_lab` permite que el perfil ficticio liste y
modifique sus eventos sin que el adaptador operativo de WhatsApp los presente como
citas de pacientes (`whatsapp_chatbot`). Google conserva la fuente de verdad; la
SQLite de voz no intenta reconstruir snapshots de un proveedor remoto. El cliente
HTML y `/lab/health` muestran el proveedor activo.

`VoiceMetrics` conserva medidas escalares por turno y costo estimado por sesion
con transcripcion separada. Primer PCM recibido, primer frame emitido por la pista
y señal en el renderizador del navegador tienen referencias distintas y explicitas.
Se registran herramientas, corte local, CPU/RSS y colas; ningun contador acredita
escucha humana ni convierte una muestra en garantia de p50/p95. Ver CA-18 de 021.
El maximo configurable por sesion Realtime es de 300 s; la inactividad real de
30 s y la cuota total por perfil se mantienen separadas. `VOICE_MAX_SESSIONS` usa
5 por defecto y acepta `unlimited` para el entorno de pruebas actual. Al agotar un
maximo numerico, el endpoint informa HTTP 429 con el conteo persistente; reiniciar
no lo borra. La cuota diaria queda pendiente antes de uso operativo.

La [especificacion 021](./specs/021-whatsapp-inbound-calling/spec.md) y su
[diseno](./specs/021-whatsapp-inbound-calling/design.md) mantienen propuesta la
integracion con Meta y autorizaciones/continuidad operativas. El runtime de texto
sigue separado del laboratorio implementado. Los siguientes componentes no
representan una integracion Calling disponible.

```text
Meta Calling / simulador
        |
        v
Webhook -> registro del evento -> ACK
        |
        v
Servicio de llamadas <-> cliente Calling HTTP / fake
        +-- sesiones y eventos -> SQLite
        +-- tareas supervisadas por FastAPI
        |
        v
Transporte de audio <-> Meta / interlocutor de laboratorio
        |
        v
Audio nativo <-> OpenAI Realtime <-> turno consolidado
                                             |
                                             v
                                   Herramientas de agenda
                                             |
                                             v
Audio <- respuesta nativa del modelo y resultado validado
```

La propuesta de [ADR 0054](./decisions/0054-inbound-calling-with-scoped-confirmation.md)
mantiene Meta directa y el flujo conversacional actual. Separa conversacion del
paciente, sesion de llamada y turno de voz. La gestion unica gana propietario de
canal/sesion y version: retomar conserva datos, revalida agenda y exige otra
pregunta, sin trasladar autorizaciones del chat o de una llamada anterior.

Antes de cualquier mutacion de voz, incluidas las rutas locales de creacion, el
backend comprobara la autorizacion para la accion exacta. La entrega escrita y
la reproduccion tendran resultados separados; un fallo de audio no autoriza
repetir una operacion de agenda. Las sesiones abiertas tras reiniciar quedaran
interrumpidas, sin reanudar automaticamente audio o herramientas.

Los cortes empiezan con dobles sin red y audio de laboratorio en la Raspberry.
`aiortc` esta adoptado para laboratorio en la ADR 0055 y OpenAI Realtime para
voz nativa en la ADR 0056. La conectividad ICE/STUN/TURN hacia Meta se concretara
antes de su verificacion. El numero real y Calling habilitado
solo bloquean el corte conectado a Meta. Una prueba de laboratorio o un webhook
saludable no acreditan audio de WhatsApp. El detalle y las salidas por corte estan
en [tasks.md](./specs/021-whatsapp-inbound-calling/tasks.md).

## Continuidad del paciente ficticio de laboratorio (ADR 0057)

`/lab/messages` y `/lab/history` comparten el perfil del servidor, su historial y
proveedor de agenda con la voz. Fake es el default; Google se selecciona
explicitamente y escribe eventos reales bajo el propietario de laboratorio. Si hay
llamada, el texto entra en esa sesion Realtime;
sin llamada `LaboratoryTextConversation` mantiene una conexion textual limitada.
El cambio a voz cierra primero esa conexion. `BookingDetails` concentra la
validacion final de nombre/motivo compartida con `ConversationService`.

Canal, secuencia y generacion los fija el backend. Retomar conserva datos y crea
otra pregunta/propuesta, sin transferir autorizaciones. Los turnos conservan
`generation_state`, `state`, `generated_ms` y `emitted_ms`: las transcripciones
actualizan su clave/orden original, y una salida interrumpida no se presenta como
completa. El texto solo se marca publicado despues de emitir el cuerpo HTTP;
los resultados pendientes de escritura se reintentan sin volver a invocar al modelo.
La continuidad con el bot/paciente operativo sigue delimitada en C4/C5.

Una pregunta de reserva cortada pierde su autorizacion, no sus datos. `VoiceTools`
conserva aparte la propuesta interrumpida durante la llamada; confirmar su ID en
el canal propietario vuelve a validar/preparar y retorna otra pregunta con ID
nuevo. Solo otra afirmacion tras emitirla completa ejecuta la accion. Rechazo,
correccion, nueva gestion y cierre descartan esa recuperacion local (ADR 0057).
Si una respuesta intermedia Realtime se cancela y crea un salto de secuencia,
`VoiceSession` liga la transcripcion al turno actual y espera hasta 1 s. Una
afirmacion inequivoca de ese turno, para la propuesta vigente cuya pregunta se
emitio completa, permite confirmarla. Sin transcripcion clara se renueva la
pregunta; no se utiliza texto de turnos anteriores ni de otra sesion (ADR 0060).

## Arquitectura objetivo

### Incremento aprobado: contexto historico de `/lab` (ADR 0061)

Contrato documentado el 21 de octubre de 2026, con apertura independiente adoptada
y comprobada con dobles (CA-22). Se propone separar tres responsabilidades: sesion
actual, antecedentes historicos del perfil y gestion/autorizacion vigentes del
backend. Cada llamada
genera su saludo con `conversation=none`, `input=[]`, `tools=[]` y `tool_choice=none`;
los turnos actuales conservan la conversacion predeterminada con historial. La
cancelacion del saludo corta audio y cancela por ID sin recortar items remotos
fuera de banda. El contexto enriquecido con fecha, canal, sesion y resultado
conocido mantiene implementacion pendiente.

La ventana reciente conserva 12 mensajes y `search_conversation_history` ya
consulta temas mas antiguos por palabras, fecha de sesion y canal, limitada al
perfil del servidor y excluyendo la sesion actual. `VoiceRepository.search_history`
usa SELECT parametrizado/read-only y retorna hasta seis fragmentos de 600
caracteres con procedencia y precision temporal declarada. La auditoria sigue en
`voice_tool_calls`. Un turno de solo consulta no invalida propuestas al finalizar
ni vincula preguntas citadas a una autorizacion actual, tanto en voz como en texto.
Los vencimientos y las reglas de interrupcion/cierre mantienen su control previo.
El resultado de una gestion se respaldara en registros de acciones/herramientas; la agenda
seguira determinando la vigencia actual. Leer antecedentes no activa gestiones ni
autoriza acciones. Retomar explicitamente revalida datos/agenda y exige propuesta
y pregunta nuevas conforme a los controles existentes de voz y texto.

La [ADR 0061](./decisions/0061-laboratory-history-and-call-boundaries.md) y los
criterios CA-22 a CA-26 de 021 fijan esa frontera para el paciente ficticio de
`/lab`; las conversaciones del WhatsApp operativo mantienen su integracion aparte.

### Direccion general

```text
WhatsApp
    |
    v
Webhook
    |
    v
Python Backend
    |
    +-- Conversation Service
    |
    v
AI Agent
    +-- LLM
    +-- Memory
    +-- RAG
    +-- Tools
          +-- Database
          +-- External APIs
          +-- n8n
    |
    v
WhatsApp Cloud API
    |
    v
Usuario
```

Esta arquitectura representa una direccion, no componentes que deban crearse
desde el inicio.

## Responsabilidades actuales

### WhatsApp Cloud API

Entrega eventos al webhook y permite enviar mensajes a WhatsApp.

### ngrok

Expone temporalmente el servidor local mediante una URL HTTPS publica. No forma
parte de la arquitectura de produccion.

### FastAPI

Define los endpoints HTTP y transforma las solicitudes en llamadas al codigo del
backend. Extrae mensajes de texto y coordina el `ConversationService`.
`reply_delivery.patient_turn()` serializa recepcion, generacion, envio y
notificaciones del mismo paciente dentro del proceso Uvicorn. El bloqueo es
compartido por servicios creados en solicitudes distintas, permite avanzar a
pacientes distintos en paralelo y se libera tambien ante errores o cancelacion.
`ReplyDeliveryService` reclama el turno, decide si esta obsoleto y recupera una
respuesta ya preparada antes de volver a generar.

### Conversation Service

Identifica al paciente de prueba por su numero de WhatsApp, busca o crea una
conversacion activa y construye un `PatientScope` con el paciente, la
conversacion y el numero de WhatsApp resueltos por el backend. Conserva el
historial y construye el contexto para el LLM. El `PatientScope` no se obtiene
de los argumentos del LLM.
El contexto comienza con las reglas del asistente y usa los mensajes mas
recientes persistidos hasta el turno actual. No incluye mensajes o respuestas
de turnos posteriores al mensaje que se procesa; el filtro temporal se aplica
antes del limite de historial. Las reglas indican que los detalles de una cita no deben
mostrar su ID interno al paciente, aunque el agente conserva ese valor para
operaciones posteriores. Tambien solicita la respuesta al proveedor LLM, convierte
las tablas Markdown accidentales en listas compatibles con WhatsApp y conserva el
resultado del envio. Recibe un `ToolExecutor` compuesto por `main.py` y crea el
`AgentOrchestrator` para ejecutar llamadas de herramientas.

Antes de enviar el contexto, agrega la fecha y hora local del reloj del
`ToolExecutor`, la zona horaria de la agenda y los rangos ISO de hoy, manana y
ayer. Esta informacion permite resolver expresiones relativas sin depender del
conocimiento temporal del modelo. Las consultas normales excluyen tombstones
cancelados de Google; una cancelacion solo aparece como resultado de la mutacion
explicita que la confirma.

Para una solicitud reconocible de agendamiento, incluidas expresiones como `sacar cita`,
que contiene un dia pero no una hora, `ConversationService` consulta primero
`check_availability` para todo ese dia. Muestra los slots libres como una lista unica y
espera la seleccion del paciente; no crea una cita ni pregunta el motivo en ese turno.
La fecha y los slots ofrecidos quedan en `conversations.context_json` durante 10 minutos.
Las listas de disponibilidad para agendar o reprogramar usan `format_patient_time()`
para mostrar solo el inicio como `- h:mm AM/PM` despues de convertir a la zona horaria
de agenda, tambien en `_resumed_workflow_prompt()` al retomar slots persistidos.
Mediodia es `12:00 PM` y medianoche `12:00 AM`, sin depender del locale.
El prompt solicita solo el inicio tambien para citas reservadas, detalles y
confirmaciones. `format_whatsapp_reply()` elimina el extremo final de los campos
de hora reconocibles, incluidas tablas convertidas y etiquetas `Hora:`/`Horario:`
fuera de listas, sin reescribir el motivo. `PendingAppointmentAction` presenta
`Hora: h:mm AM/PM` y el inicio nuevo de reprogramacion con el mismo formato.
La lectura de las horas del ultimo listado acepta AM/PM, tanto con solo el inicio
como con los rangos historicos;
los slots persistidos y los contratos de herramientas conservan sus fechas ISO.
Si la solicitud inicial no contiene dia ni hora exacta, el backend guarda
`pending_appointment_date`, pregunta el dia y resuelve una respuesta relativa posterior,
como `hoy`, directamente contra `check_availability`. La solicitud pendiente tambien
expira a los 10 minutos.
Cuando el paciente elige una hora, el backend la valida contra ese estado y crea la
solicitud pendiente de cita directamente, por lo que las preguntas de nombre y motivo
no dependen de una respuesta textual del LLM. Las solicitudes con hora exacta continúan
por el flujo normal y conservan la interceptacion de `create_appointment` como defensa.

### Interpretacion hibrida de la seleccion pendiente

`appointment_slot_selection.PendingSlotSelectionInterpreter` obtiene una sola
interpretacion por turno sobre el snapshot activo o pausado. Las selecciones
completas reconocidas, incluido `si a las 9 am estaria bien`, usan la via local.
El router conserva sus rutas para abandono, gestiones nuevas y preguntas informativas.
Solo el lenguaje restante consulta `LLMProvider.generate_text`, que no publica
herramientas. El JSON contiene `intent`, `slot_id` y evidencia literal; el prompt
recibe fecha, zona y slots con referencias efimeras, sin IDs de cita/paciente,
historial ni motivo de consulta. No se agregan dependencias o configuracion.

El backend exige un esquema exacto, evidencia presente en el mensaje y pertenencia
del slot al snapshot. Si hay una hora numerica o una referencia reconocible como
`las nueve`, tambien comprueba su coincidencia
unica y valida minutos y AM/PM; el modelo no sustituye una hora no disponible por
otra. Condiciones, negaciones, varias horas, preguntas tentativas y referencias a
otras fechas se excluyen localmente del evaluador. Una respuesta invalida o un
fallo del proveedor pide aclaracion sin modificar el estado o la agenda.
El servicio registra el tipo de fallo y codigo HTTP en `llm_failures`; las
respuestas estructuradas invalidas se registran como `InvalidSlotSelectionResponse`,
sin copiar el mensaje o el contenido del proveedor. Las afirmaciones aisladas
no permiten escoger un horario. Las cantidades y representaciones redundantes
de una misma hora no se confunden con dos opciones distintas.
Las comparaciones conservan minutos y AM/PM, mediante el patron compartido de
`time_selection_references()`; no deduplican 9:00/9:30 ni mañana/noche.

`ConversationService` pasa el resultado explicitamente a recuperacion, enrutamiento
y seleccion. No existe un cache mutable compartido entre pacientes ni una segunda
interpretacion del mismo mensaje. Las listas vencidas no invocan al modelo; retomar
refresca su disponibilidad. La seleccion valida prepara el nombre/motivo o una
confirmacion nueva, y las confirmaciones de cambios siguen siendo locales.
Detalle en `specs/019-hybrid-slot-selection/` y ADR 0050.

### Modelo de dominio de citas

`calendar_domain.py` define `Appointment`, `AvailableSlot`, `PatientScope`,
`ToolRequest`, `ToolResult` y el protocolo `CalendarProvider`. El dominio valida
invariantes, normaliza los cinco contratos y separa el alcance confiable del
paciente de los argumentos conversacionales. `ToolExecutor` ejecuta las
solicitudes del backend contra el proveedor configurado, sin realizar llamadas
de red por si mismo.

`tool_contracts.py` define los inputs y outputs especificos de cada herramienta.
`tool_validation.py` valida fechas, horarios, conflictos, pertenencia y estados
antes de cualquier proveedor. `tool_results.py` convierte las excepciones de la
frontera de agenda en `ToolResult.failure()` sin copiar detalles internos.
`FakeCalendarProvider` implementa el contrato en memoria con datos deterministas,
periodos ocupados, conflictos y fallos simulables. El `ToolExecutor` se encarga
de parsear, validar, despachar cada operacion y envolver su salida en el output
tipado correspondiente. `list_appointments` conserva el alcance del paciente,
acepta un rango opcional por superposicion y no restringe consultas historicas.
En el esquema del proveedor, cada extremo opcional admite una fecha ISO o `null`;
ambos valores nulos equivalen a omitir el rango, mientras que un rango incompleto
sigue siendo rechazado por el contrato.
La suite verifica esta frontera sin Google Calendar.

### Persistence y repositories

`persistence.py` administra conexiones, esquema y transacciones SQLite.
`repositories.py` encapsula las operaciones de pacientes, conversaciones y
mensajes y citas. La ruta de la base se configura mediante `DATABASE_PATH`.
La tabla `llm_failures` conserva el tipo de excepcion y un codigo HTTP nullable para
los errores del proveedor; las bases existentes reciben esa columna mediante una
migracion aditiva. El log registra solo esos campos y omite el texto entrante, el cuerpo
del proveedor y las credenciales.
El modo debug opcional usa `DEBUG_MODE` y `DEBUG_WHATSAPP_NUMBERS`: solo un remitente
permitido recibe el nombre seguro del proveedor, el tipo de error y el codigo HTTP, o un
codigo publico de agenda, junto con la respuesta. La allowlist exige numeros E.164 con
`+` explicito; el signo se valida en la configuracion y luego se normaliza para comparar
con el remitente de WhatsApp. Sin ambas condiciones, todos reciben la respuesta
controlada/publica normal. El modo no expone mensajes de excepcion, prompts, cuerpos ni
encabezados HTTP.
`reply_outbox` conserva una respuesta unica por mensaje entrante y sus eventos
de cita, preparados antes del envio. Los estados de procesamiento y transporte
se separan de los estados historicos de `messages`. `ReplyDeliveryRepository`
encapsula la reclamacion y las transiciones, junto con `reply_delivery_attempts`,
que conserva inicio, final, estado e ID del proveedor por intento. Los reintentos
con turnos posteriores ya procesados quedan en `superseded`; los mensajes
posteriores solamente recibidos no vuelven obsoleto al anterior. Los resultados
inciertos quedan en `uncertain` y no autorizan otra generacion o envio.
La tabla `appointments` conserva el ID interno de la cita, el calendario y evento
de Google, el paciente, el estado, el intervalo, el motivo y las fechas de
sincronizacion. `PersistentCalendarProvider` traduce el ID interno expuesto a las
herramientas al `google_event_id` que necesita el proveedor externo. Google
Calendar sigue siendo la fuente de verdad; SQLite conserva la identidad local y
el ultimo estado sincronizado.

### WhatsAppClient

Construye la solicitud autenticada de tipo texto para WhatsApp Cloud API usando
`WHATSAPP_ACCESS_TOKEN` y `WHATSAPP_PHONE_NUMBER_ID`. No contiene logica de
conversacion.

### Confirmacion al paciente y bloques compartidos

`appointment_messages.render_appointment_message()` construye los bloques de cita
y paciente para las dos audiencias, compartiendo etiquetas, estados y telefono de
10 digitos. El paciente recibe `CONFIRMACION DE CITA`, fecha `DD/MM/YYYY` y solo el
inicio con AM/PM; el doctor conserva encabezado interno, fecha ISO e intervalo.
`ConversationService._appointment_result_reply()` usa el output tipado definitivo,
la zona de agenda y el nombre persistido para crear, cancelar y reprogramar. No
depende del resumen ni realiza una llamada adicional al LLM. La respuesta se
prepara y persiste antes de enviarse, con el mismo flujo idempotente del webhook.
El compositor del doctor sanea sus campos antes de delegar los bloques compartidos
y agrega resumen/prioridad despues. Spec 020 y ADR 0053 registran el alcance.

### Notificaciones al doctor

La captura y la disponibilidad del transporte son independientes. Con
`DOCTOR_NOTIFICATION_TRANSPORT=template`, nombre o idioma pendientes conservan
las entregas en `pending` con un motivo y sin llamadas de resumen/envio. La puerta
se aplica en el disparador y en el entregador. Las bandejas existentes guardan el
evento: chat mantiene `notifications_completed=0` en `reply_outbox`; ambos canales
lo recuperan en sus ciclos de lifespan, incluso sin otro mensaje del paciente.
Los marcadores de composicion diferida nunca se despachan. El transporte omitido
mantiene `text` por compatibilidad. El adaptador de plantillas requiere tambien un
mapeo explicito de componentes; completar dos variables no acredita aprobacion de Meta.

Limite operativo comprobado: el modo `text` envia texto libre, sujeto a la
ventana de 24 h iniciada por un mensaje del doctor al numero del bot. Meta puede
aceptar el POST y luego devolver `failed/131047`. El `sent` local actual significa
aceptacion inicial, no recepcion. `delivery_status` distingue esa aceptacion de los
estados confirmados por Meta. El envio por plantilla y los callbacks estan
implementados, con `aviso_cita_medico` en `es_MX` y sus nueve parametros de cuerpo
configurados en 011. Una prueba directa de esa plantilla obtuvo `delivered` real
el 25/10/2026; evidencia en `verification/2026-10-25-approved-template-delivered.md`.
La integracion de voz no elimina esas
restricciones de WhatsApp.

Los callbacks entran a `whatsapp_delivery_receipts` en la base de chat antes de
confirmarse al proveedor. `notification_statuses.py` correlaciona por ID y
destinatario con intentos de chat y voz; proyecta en segundo plano y recupera
pendientes cada 5 s. Una transaccion por destino y el ACK individual del inbox
permiten reaplicar tras reiniciar sin perder callbacks tempranos, duplicar
programaciones ni retroceder estados. Solo se guardan codigos de error seguros.
La base de voz conserva su esquema e identidades aislados.

`notification_template.py` adapta los datos saneados del compositor al orden y
agrupacion del JSON de componentes configurado. El cuerpo y `template_data_json`
se congelan por evento; al reclamar la entrega se conserva `template_payload_json`
con nombre, idioma y componentes. Las bases de chat y voz usan una migracion
compartida y opcional para esos snapshots. `WhatsAppClient.send_template()` utiliza
el mismo HTTP de texto y el destinatario de la entrega, sin un servicio adicional.
El mapeo real esta en `specs/011-doctor-notifications/approved-template.md`. El
encabezado fijo se renderiza en Meta; solo se proporcionan los nueve parametros
de cuerpo. El contrato real se prueba con HTTP simulado ademas de los layouts
ficticios del adaptador generico.

`notification_recovery.py` comparte el ciclo de arranque/polling entre los
adaptadores de chat y laboratorio. `notification_retry.py` clasifica los fallos y
calcula la espera persistida. La elegibilidad tambien se exige al reclamar en SQL.
Los rechazos de configuracion quedan detenidos por huella relevante; `sending`
incierto espera conciliacion explicita. No se liberan reclamaciones por tiempo.
`doctor_notification_attempts` audita contenido, version local y parametros de cada
despacho y su conciliacion. La bandeja guarda evento y contexto congelados, de
modo que su recuperacion no depende de volver a consultar o modificar la agenda.

`notification_trigger.py` es la entrada comun de chat y voz/texto de `/lab` para
composicion y entrega. Ambas entradas usan la conversion tipada de
`notification_domain.py`, el mismo compositor, bloques, destinatarios y cliente
WhatsApp. El webhook conserva la entrega posterior a la respuesta al paciente.
`VoiceTools` guarda el evento con el resultado definitivo y despierta a
`VoiceDoctorNotifications`, una tarea del lifespan que recupera pendientes al
arrancar y cada 60 s, sin añadir latencia de resumen/envio al turno de audio.

La SQLite exclusiva de voz agrega `voice_notification_events` y reutiliza
`doctor_notifications` mediante `notification_schema.py`; conserva identidades
ficticias sin referencias a la base operativa. Nombre y limites de secuencia se
congelan por evento; el contexto solo incluye transcripciones disponibles de la
sesion/gestion y salidas completas. La clave `voice:<sesion>:<accion>:<herramienta>`
evita colisiones con chat y otras llamadas. No se notifican retroactivamente
acciones antiguas que carecen de evento persistido. El perfil ficticio no tiene
telefono vinculado y el mismo formato presenta `Telefono: No informado`.

Un reintento reutiliza el cuerpo preparado y nunca ejecuta de nuevo la agenda.
Los fallos previos de resumen permiten completar el cuerpo antes del primer
envio. Una fila ya reclamada no puede enviarse concurrentemente; `sending` incierto
queda para conciliacion. El detalle esta en RF-1111 de 011 y ADR 0019 ampliada.

Esta capacidad esta implementada en `specs/011-doctor-notifications/`. Los cortes 1
a 5 implementaron la emision de eventos internos despues de una operacion exitosa
de `create_appointment`, `reschedule_appointment` o `cancel_appointment`, una
bandeja SQLite persistente, la composicion segura del cuerpo, la entrega aislada
por destinatario y la integracion con el webhook.

`DoctorNotificationService` carga el paciente y el historial persistido.
`DoctorNotificationComposer` construye un unico cuerpo logico con el tipo de evento,
los datos de la cita, el paciente, los ultimos 10 digitos del telefono, el resumen
conversacional y las señales de prioridad disponibles. Las señales usan un catalogo
compartido de descripciones operativas y nunca incluyen diagnosticos. Ese cuerpo se
entregara a cada doctor configurado.
El resumen sera contenido de cada notificacion y no un disparador independiente.

La composicion usa `generate_text()` con un prompt interno sin herramientas. El
resumidor recibe el motivo y el historial, sin campos estructurados de agenda, y
se instruye para resumir la charla con el paciente (motivo, molestias, dudas y
detalles relevantes), omitiendo fecha, horario, zona, estado y confirmacion de la cita
incluso si aparecen en el historial. Un motivo general no autoriza inventar sintomas.
El resultado del LLM se valida y se limita; los diagnosticos, recomendaciones,
transcripciones completas y valores internos conocidos se descartan o sustituyen
por contenido seguro antes de formar el cuerpo.

La misma llamada analiza semanticamente el motivo y el historial de la gestion actual.
Las señales del modelo requieren `priority_signal_evidence` con codigo soportado y
cita literal encontrada en el motivo o en mensajes entrantes; no requieren una segunda
coincidencia con palabras clave. El respaldo local se combina con ese resultado,
incluyendo secrecion ocular amarillenta, verdosa o abundante como `ocular_discharge`.
El repositorio de notificaciones marca el limite con el ultimo evento anterior de esa
conversacion, independientemente del estado de entrega, y el compositor reconoce
ademas respuestas fijas de exito del backend, incluidas las confirmaciones por
bloques y los cierres historicos. El limite de historial se aplica despues
de separar gestiones. Se excluyen mensajes futuros y se conserva la respuesta enviada
del evento actual; los mensajes del asistente no son evidencia de sintomas.

`DoctorNotificationDeliveryService` carga la configuracion de destinatarios,
reutiliza `WhatsAppClient` y procesa cada fila mediante una reclamacion atomica.
Los envios exitosos quedan en `sent` con el ID de Meta; los fallos se normalizan y
quedan en `failed` sin detener a los demas destinatarios. Las filas enviadas no se
reclaman otra vez y las fallidas pueden reintentarse posteriormente. El servicio de
agenda no envia mensajes directamente.

```text
ToolExecutor
    |
    +-- CalendarProvider
    |
    +-- AppointmentNotificationEvent
            | (collector por solicitud)
            v
    respuesta al paciente confirmada
            |
            v
    DoctorNotificationTrigger -> SQLite -> DoctorNotificationDeliveryService
                                      -> WhatsAppClient -> Doctores configurados
```

`main.py` recolecta los eventos durante `ConversationService.build_reply()` y
guarda su snapshot junto con la respuesta preparada. Despues
de enviar y persistir la respuesta del paciente, compone el resumen y llama a
`DoctorNotificationDeliveryService` por cada evento. La entrega al doctor se
encapsula en un limite de errores: una falla de configuracion, composicion,
persistencia o WhatsApp se registra sin propagarse al paciente; el servicio de
entrega mantiene ademas el aislamiento entre destinatarios.
Un reintento de envio carga el snapshot, sin repetir una mutacion para reconstruir
el evento. Si se interrumpe despues de persistir el envio al paciente pero antes
de finalizar las notificaciones, el duplicado puede completar estas sin volver a
enviar al paciente. El incremento se define en `specs/018-safe-webhook-retries/`.

### Confirmacion de cambios de citas

La funcionalidad definida en `specs/012-appointment-change-confirmation/` intercepta
las solicitudes de cancelacion y reprogramacion antes de `ToolExecutor`. La accion
exacta queda pendiente en `conversations.context_json` hasta que el paciente
responde afirmativamente. `classify_action_confirmation()` interpreta respuestas
completas respecto de la herramienta pendiente y acepta cortesia alrededor de
afirmaciones o negaciones claras. `Si cancelala` y `Cancela la cita por favor`
confirman una cancelacion ya mostrada; no crean una accion por si mismas.
Señales contradictorias, preguntas tentativas y texto no reconocido no autorizan
mutaciones. El reconocimiento completo excluye otras citas, fechas, horas y
comandos adicionales; no se usa el clasificador generico como respaldo permisivo.
`Si es correcto`, `Si esta bien` y `Correcto, por favor` resuelven esa accion en
el primer turno claro. Un `si` posterior sin acento se considera posible condicion
antes de normalizar; no autoriza una mutacion por coincidencia de frases.
Las dudas usan `PendingAppointmentAction.clarification_prompt()` con el reloj de
agenda para mostrar la cita original y el destino guardado. Ese texto conserva
el snapshot y su vigencia, y se construye sin llamadas al LLM.
Antes de preguntar, `ConversationService` usa una lectura
del `ToolExecutor` para conservar fecha, horario y motivo de la cita en el snapshot
de la accion; esos datos se muestran sin el ID interno. Si no recupera la cita o la
lectura falla, devuelve el error publico de agenda y no guarda accion pendiente. Una
respuesta negativa o vencida no llama a una mutacion del calendario. Solo la ejecucion
confirmada puede producir un evento de cita y una notificacion al doctor.
Rechazar o abandonar una accion informa que no hubo cambios y que la cita original
sigue agendada, con su fecha y hora cuando estan disponibles en el snapshot.

Para una cancelacion directa, `is_cancellation_request()` dirige el mensaje a una
lectura backend de agenda antes del agente. La referencia de fecha explicita prevalece
sobre el ultimo listado; hora, minutos y AM/PM filtran candidatos sin sustitucion
silenciosa. Una coincidencia unica vuelve a resolverse y se persiste como accion
antes de mostrar la primera pregunta. El primer `si por favor` ejecuta esa misma
accion tras un reinicio; no inicia otra confirmacion. Candidatas ambiguas o ausentes
reciben una aclaracion de identidad sin mutacion.
Una pregunta textual reconocible del LLM sin accion pendiente se reemplaza por
una solicitud de dia/horario, y una afirmacion aislada no permite al agente crear
una cancelacion desde el historial. Las pausas, expiracion y entrega idempotente
siguen conservando sus fronteras existentes.

Antes de crear una confirmacion de reprogramacion, `ConversationService` consulta la
disponibilidad del dia de destino completo. La respuesta conserva los slots ofrecidos,
el ID de la cita y el ID de llamada en el contexto por 10 minutos. Solo una seleccion
coincidente produce una accion pendiente de confirmacion; el intento de seleccionar una
hora fuera de la lista no genera una mutacion.
Una hora reconocida sin coincidencias explica que esta ocupada o no disponible,
en vez de afirmar que no se entendio. `matching_slots()` distingue esa ausencia
de una ambiguedad AM/PM; ambas conservan la cita y la lista pendiente.

Si el paciente solicita cambiar solo la hora, `ConversationService` identifica la cita
en el ultimo listado persistido y presenta la disponibilidad de ese dia antes de pedir
una hora preferida. Si no consigue resolver una unica cita, solicita que el paciente
precise cual desea modificar.

### Enrutamiento de intencion durante flujos pendientes

La funcionalidad definida en `specs/016-conversation-intent-routing/` consulta el
mensaje mas reciente antes de resolver fechas, selecciones, datos de reserva o
confirmaciones pendientes. `conversation_intent.py` identifica continuacion, abandono,
aclaracion, pausa informativa y cambio explicito de tarea. Abandonar o cambiar de tarea limpia los estados
de agenda en una sola actualizacion de contexto; una intencion nueva vuelve al flujo
normal y conserva las confirmaciones de seguridad existentes. Una expresion ambigua
como `cancela` solicita aclaracion y no borra estado ni ejecuta una mutacion. Una
confirmacion descartada no puede ejecutarse con un `Si` posterior.
Antes del router generico, una respuesta completa sobre la accion pendiente va a
su resolucion: el verbo de cancelar no significa una tarea nueva si confirma esa
misma cancelacion. Una contradiccion conserva la accion y pide aclarar, sin
confundirla con abandono. Durante una pausa, esa respuesta solo pide retomar;
una negativa clara descarta la gestion sin mutacion. `cancela` aislado en una
cancelacion activa mantiene el estado y formula una unica pregunta de si/no.
Una expresion completa de seleccion, como `agendame a las 11 am`, continua el flujo
si corresponde a la lista; una hora dentro de otra instruccion no cuenta como eleccion.
Tambien se reconocen `quisiera una cita a las 9 am`, `necesito una cita a las 9 am`
y `me gustaria una cita a las 9 am`, con saludo y cortesia opcionales. El patron
completo conserva la fecha ofrecida y la transicion backend hacia nombre y motivo;
una fecha adicional o una solicitud de `otra cita` sigue iniciando otra gestion.
El reconocimiento repara puntos, comas o punto y coma entre palabras y acepta
`esta bien/me parece bien` al final de una seleccion completa. Conserva los
separadores numericos de horas como `10.30` y los signos de pregunta.
`normalize_time_selection_punctuation()` se comparte con la lectura de hora y
la deteccion de periodo explicito: `10 de.la.noche` conserva las 10 PM y nunca
se sustituye por una opcion disponible a las 10 AM.
La aclaracion de reserva y reprogramacion comparte la comparacion de slots:
una hora valida con cero coincidencias informa no disponibilidad, varias
coincidencias piden AM/PM y una hora invalida recibe la aclaracion de formato.
Estas respuestas conservan la lista activa o pausada sin efectos de agenda.
Los saludos y preguntas informativas mueven el snapshot tipado de
`conversation_workflow.py` a `paused_conversation_workflow` dentro del mismo contexto
SQLite. La transaccion conserva solo una gestion activa o pausada y el agente recibe
un recordatorio operativo independiente del historial recortado. Sus solicitudes de
mutacion se interceptan mientras responde otro tema con una gestion pausada.

La seleccion contextual de reprogramacion admite verbos de cambio, preferencias
y peticiones corteses completas, sin confundir `quisiera cambiarla a las 12 pm`
con otra gestion. El reconocimiento anclado mantiene fuera otras citas, fechas
adicionales y comandos. `appointment_availability.py` interpreta mediodia como
12:00 PM y conserva la comparacion en la zona horaria de agenda. Un periodo
incompleto solo activa aclaracion; no se considera respuesta esperada ni borra
el snapshot. Las selecciones validas llegan al flujo existente de confirmacion.

Retomar restaura el paso pendiente y los datos recibidos. Las fechas y selecciones
claras pueden retomarlo implicitamente; un `Si` no reactiva una confirmacion pausada.
La pausa conserva los vencimientos: renovar slots requiere una consulta de agenda;
`name_message_id` acompaña la misma reserva en fecha/disponibilidad renovadas.
Las acciones se vuelven a resolver contra la agenda y requieren confirmaciones
nuevas. Las instrucciones de olvidar la actividad y las nuevas gestiones explicitas
siguen descartando el snapshot anterior.

### Motivo antes de crear una cita

La funcionalidad definida en `specs/013-appointment-reason-collection/` intercepta
`create_appointment` antes de `ToolExecutor`. `ConversationService` guarda el
horario en `conversations.context_json`, solicita el nombre en cada cita nueva y lo
valida con `patient_name_validation.py`. Actualiza `patients.name` solo al aceptarlo,
aunque ya existiera, muestra el nombre completo guardado y despues pregunta el motivo. El
valor que el LLM haya propuesto se descarta. El
mensaje que entrega el nombre queda marcado en el estado pendiente para que un
reintento no se use como motivo. El siguiente mensaje de motivo se normaliza solo en
espacios y se usa como `reason` para ejecutar la cita; referencias vagas como `Lo de
siempre` se conservan pendientes y solicitan aclaracion.

La politica minima de ADR 0048 acepta una descripcion oftalmologica general,
sin exigir diagnostico, intensidad ni duracion. `apply_minimum_reason_policy()`
combina un respaldo positivo de expresiones completas con categorias oftalmologicas
reconocidas con confianza por el evaluador. Si el respaldo local resuelve una
evaluacion insuficiente o fallida, registra `rules` sin atribuir su confianza al LLM.
Sin respaldo suficiente, distingue fallo tecnico, incertidumbre y falta de motivo.
Las aclaraciones reconocen el texto/referencia recibidos y `attempt_count` cambia la
pregunta desde el segundo intento; no se añade una migracion de persistencia.

El validador del nombre distingue entradas invalidas de partes que necesitan
confirmacion; no usa un diccionario ni modifica la escritura. Las señales de texto
de prueba se aplican por palabra latina y no se extrapolan a otros alfabetos.
Antes de aceptar un nombre, reglas de frase normalizadas por acentos y mayusculas
descartan recordatorios como `ya te lo habia dich`, negativas a proporcionarlo y
expresiones reconocibles de sintomas como `Tengo los ojos rojos`. Estas reglas
no se aplican a palabras sueltas de un apellido ni corrigen el texto guardado.
Un rechazo conserva el nombre previo, el candidato y el horario. El nombre aceptado
y `name_required=false` siguen siendo autoritativos en esa reserva tras un reinicio.
`PendingAppointmentReason` conserva `name_candidate`, `name_required=true` y el
ultimo `name_clarification_message_id` en el mismo JSON. Una afirmacion explicita
acepta ese candidato completo; un nuevo nombre se valida de nuevo y una negativa
pide reescribirlo sin abandonar la reserva. La captura aceptada y el cambio de paso
se guardan en una transaccion. Los reintentos de mensajes de aclaracion anteriores
no reemplazan el candidato actual ni se usan como motivo. Una pausa conserva el
candidato y retomarla vuelve a mostrar la aclaracion; un `Si` aislado no lo acepta
mientras la gestion esta pausada.

La primera pregunta no modifica la agenda ni genera eventos. Una creacion exitosa
posterior conserva el mismo flujo de respuesta, persistencia y notificacion al
doctor. Las señales de prioridad se derivan de codigos limitados, se registran en la
evaluacion y se convierten en lenguaje operativo sin diagnosticos antes de la
notificacion. Una solicitud vencida despues de 10 minutos se limpia sin tocar el
proveedor. La politica clinica para pacientes reales permanece fuera del alcance.

El catalogo detecta `eye_redness` en frases como `Tengo los ojos rojos` y
`ocular_discharge` en `Tengo laga;as muy amarillentas y grandes en los ojos`.
El evaluador previo a agendar analiza el motivo, mientras que la notificacion incorpora
ademas los mensajes del paciente de la gestion actual. Los prompts comparten catalogo
e instrucciones semanticas; las sugerencias del modelo requieren evidencia literal.
Las reglas locales excluyen negaciones explicitas y una negacion posterior del mismo
sintoma puede reemplazar su mencion anterior. No se fuerza prioridad para pocas lagañas
al despertar o una revision rutinaria.

### LLMProvider y agente LLM basico

Define el contrato asincrono `generate(messages)` para que el agente basico y la
logica conversacional no dependan de un proveedor concreto. El adaptador
`OpenAICompatibleLLMProvider` usa `httpx` y variables de entorno para Groq,
OpenAI u OpenRouter. `LLM_PROVIDER` selecciona el proveedor; las claves y los
modelos se pueden configurar por proveedor para que alternar entre Groq y OpenAI
solo requiera cambiar ese selector. `LLM_API_KEY` y `LLM_MODEL` tambien pueden
contener los valores del proveedor activo; en ese caso se actualizan al cambiar
de proveedor. El ID de `LLM_MODEL` se envia sin transformacion y debe admitir
la ruta y function calling del proveedor. OpenAI utiliza `/responses`; Groq y
OpenRouter utilizan `/chat/completions`. El adaptador transforma los cinco
esquemas compartidos al formato de cada endpoint y normaliza texto/tool calls a
`LLMResponse`.

El adaptador participa en el flujo del webhook mediante la inyeccion de
`LLMProvider` en `ConversationService`. `generate()` devuelve texto o un
`ToolCall` normalizado. `main.py` crea `BusinessHours` y `ToolExecutor`;
`create_calendar_provider()` usa `FakeCalendarProvider` por defecto o
`GoogleCalendarProvider` cuando `CALENDAR_PROVIDER=google`.
`create_availability_provider()` puede seleccionar Google solamente para
`check_availability` cuando `CALENDAR_AVAILABILITY_PROVIDER=google`; las otras
operaciones siguen usando el proveedor principal. `ConversationService` entrega
el ejecutor al `AgentOrchestrator`, que coordina las llamadas, limita las
iteraciones y devuelve la redaccion final. `main.py` coordina el envio y el
registro, pero no decide el contenido conversacional.

`create_business_hours()` carga `BUSINESS_WORKDAYS`, `BUSINESS_HOURS_START` y
`BUSINESS_HOURS_END` desde el entorno. La zona horaria se comparte con
`GOOGLE_CALENDAR_TIMEZONE`; los valores predeterminados solo mantienen el horario
tecnico inicial de lunes a viernes, 09:00-17:00.

La suite automatizada implementa el mismo contrato con `FakeLLMProvider`, que
registra las solicitudes y permite simular texto, tool calls y errores sin red.

### AgentOrchestrator

`agent_orchestrator.py` ejecuta el ciclo `LLM -> ToolRequest + PatientScope ->
ToolExecutor -> ToolResult -> LLM`. El alcance se recibe desde
`ConversationContext`; el LLM solo entrega el nombre y los argumentos
conversacionales. Los resultados enviados al siguiente turno se sanea para
excluir identificadores internos de paciente y calendario. Conservan el ID
interno de las citas para que el agente pueda solicitar cambios posteriores; la
redaccion final instruida por `ConversationService` no lo presenta al paciente y
presenta cada cita listada como un bloque con las etiquetas `*Horario:*` y
`*Motivo de consulta:*`, usando negrita compatible con WhatsApp. No usa tablas ni
HTML. `format_whatsapp_reply()` mueve el valor del motivo a la linea siguiente si
el LLM lo devuelve junto a la etiqueta o con lineas vacias intermedias. El limite
de iteraciones se configura
mediante `LLM_MAX_TOOL_ITERATIONS`. La composicion de runtime se define en
`main.py`; `create_calendar_provider()` es el punto de seleccion del proveedor.

### Uvicorn

Ejecuta la aplicacion ASGI y gestiona las conexiones HTTP.

### Google Calendar

Es la fuente de verdad opcional de la agenda del medico durante el MVP tecnico.
Alli se administran las citas, los dias no laborables y los espacios bloqueados
manualmente. El backend lo consulta y modifica mediante herramientas controladas;
el LLM no recibe credenciales ni acceso directo al calendario.

`GoogleCalendarProvider` usa por defecto el propietario privado
`managed_by=whatsapp_chatbot`. El laboratorio Realtime puede inyectar el valor
`whatsapp_voice_lab` en el mismo adaptador: sus operaciones quedan en el calendario
configurado, pero el backend de WhatsApp no los lista ni modifica como citas
operativas.

Cada cita creada por el chatbot ocupara 30 minutos. Antes de ofrecer o reservar
un horario, el backend debera comprobar tanto que el espacio no este ocupado
como que pertenezca al horario de atencion configurado.

La integracion opera sobre calendarios que ya estan en uso y contienen eventos
anteriores. El backend conserva esos eventos y no puede eliminarlos, reemplazarlos
ni reinterpretarlos sin una regla explicita. Para calcular disponibilidad combina:

- Horario laboral del medico.
- Citas existentes.
- Dias festivos o no laborables.
- Ausencias del medico.
- Espacios bloqueados manualmente.

Los eventos existentes sin metadatos del sistema no se consideran citas
administradas por el chatbot; para que una cita creada manualmente sea visible al
paciente, la descripcion debe contener una linea `WhatsApp: +<E.164>` que coincida
exactamente con su numero. El adaptador puede listar otros eventos de forma indirecta
como periodos ocupados para disponibilidad.

La API de Google Calendar puede consultar los periodos ocupados de uno o varios
calendarios. Tambien expone algunos tipos especiales, como eventos de fuera de
oficina, pero los eventos normales no indican automaticamente si representan
una cita medica, un bloqueo o una actividad personal. Por ello, la disponibilidad
tratara todos los periodos ocupados de los calendarios seleccionados como no
disponibles, sin importar su titulo o categoria y sin necesitar interpretar su
contenido.

`GoogleCalendarProvider` usa `freeBusy` para consultar hasta 50 calendarios
configurados y `events.list` con paginacion y `showDeleted=false` para localizar las
citas vigentes del paciente. Las mutaciones usan `sendUpdates=all`: no hay asistentes
agregados por el adaptador, pero se evita el modo `none`, que Google advierte que
puede perder eventos o impedir su sincronizacion.
Los eventos creados por el chatbot llevan propiedades extendidas privadas
`managed_by=whatsapp_chatbot` y `patient_id`. Los eventos creados por el medico o su
secretaria se asocian mediante una linea completa `WhatsApp: +<E.164>` en la
descripcion, comparada con el numero resuelto desde el webhook. Las operaciones de
lectura y modificacion aceptan una de esas dos asociaciones; un nombre coincidente,
un numero parcial o un evento sin marcador no bastan. El marcador se elimina del
motivo antes de serializar la cita al LLM.

La herramienta `list_appointments` entrega a la capa conversacional las citas
administradas o asociadas por telefono al paciente, incluyendo su ID interno para
futuras operaciones de reprogramacion o cancelacion. El serializador del agente omite
el calendario y el `PatientScope` antes de devolver el resultado al LLM.

La autenticacion admite OAuth con refresh/access token y cuentas de servicio,
incluida delegacion de dominio opcional. `google-auth` refresca los tokens y
`httpx` transporta las llamadas REST. Los errores de red y de Google se reducen a
los errores publicos del dominio.

Referencias oficiales:

- [Consulta de disponibilidad](https://developers.google.com/workspace/calendar/api/v3/reference/freebusy/query)
- [Tipos de evento](https://developers.google.com/workspace/calendar/api/v3/reference/events)
- [Lista de eventos](https://developers.google.com/workspace/calendar/api/v3/reference/events/list)
- [Insercion de eventos](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert)
- [Actualizacion parcial](https://developers.google.com/workspace/calendar/api/v3/reference/events/patch)
- [Propiedades extendidas](https://developers.google.com/workspace/calendar/api/guides/extended-properties)
- [Paginacion](https://developers.google.com/workspace/calendar/api/guides/pagination)

## Flujo de una herramienta de agenda

```text
Mensaje del paciente de prueba
    |
    v
LLM solicita una herramienta
    |
    v
Backend valida la solicitud
    |
    v
 Google Calendar
    |
    +-- excepcion externa -> error publico seguro
    v
 Resultado de la herramienta
    |
    v
LLM redacta la respuesta
```

## Limites actuales

- El backend solo mantiene estado conversacional basico.
- El contexto usa una ventana acotada del historial y no incluye respuestas de
  WhatsApp registradas como fallidas.
- SQLite se usa para una unica instalacion del MVP y no para multiples replicas.
- Los secretos se proporcionan mediante variables de entorno y no se guardan
  en el repositorio.
- Las pruebas automatizadas cubren el ciclo con dobles locales y el limite HTTP de
  Google Calendar; la suite no valida la disponibilidad de un proveedor LLM o una
  cuenta de Google reales.
- La migracion incremental puede consultar disponibilidad real mientras las
  operaciones de escritura permanecen en el proveedor fake.

## Preguntas abiertas

- ¿Donde se desplegara inicialmente el backend de produccion?
- ¿Se procesaran los eventos dentro de la solicitud o mediante una cola cuando
  aumente el volumen?
