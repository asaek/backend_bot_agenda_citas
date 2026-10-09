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
FastAPI parsea mensajes de texto
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

## Arquitectura objetivo

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
Las listas de disponibilidad y opciones de cita usan `format_patient_time()` para
mostrar cada extremo en formato `h:mm AM/PM` despues de convertir a la zona horaria
de agenda. Mediodia es `12:00 PM` y medianoche `12:00 AM`, sin depender del locale.
El prompt solicita ese formato para listas del LLM y `format_whatsapp_reply()`
normaliza sus campos de hora reconocibles, incluidas tablas convertidas, sin
reescribir el motivo. La lectura de las horas del ultimo listado acepta AM/PM;
los slots persistidos y los contratos de herramientas conservan sus fechas ISO.
Si la solicitud inicial no contiene dia ni hora exacta, el backend guarda
`pending_appointment_date`, pregunta el dia y resuelve una respuesta relativa posterior,
como `hoy`, directamente contra `check_availability`. La solicitud pendiente tambien
expira a los 10 minutos.
Cuando el paciente elige una hora, el backend la valida contra ese estado y crea la
solicitud pendiente de cita directamente, por lo que las preguntas de nombre y motivo
no dependen de una respuesta textual del LLM. Las solicitudes con hora exacta continúan
por el flujo normal y conservan la interceptacion de `create_appointment` como defensa.

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
codigo publico de agenda, junto con la respuesta. Sin ambas condiciones, todos reciben la
respuesta controlada/publica normal. El modo no expone mensajes de excepcion, prompts,
cuerpos ni encabezados HTTP.
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

### Notificaciones al doctor

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
resultado del LLM se valida y se limita; los diagnosticos, recomendaciones,
transcripciones completas y valores internos conocidos se descartan o sustituyen
por contenido seguro antes de formar el cuerpo.

La misma llamada analiza semanticamente el motivo y el historial de la gestion actual.
Las señales del modelo requieren `priority_signal_evidence` con codigo soportado y
cita literal encontrada en el motivo o en mensajes entrantes; no requieren una segunda
coincidencia con palabras clave. El respaldo local se combina con ese resultado,
incluyendo secrecion ocular amarillenta, verdosa o abundante como `ocular_discharge`.
El repositorio de notificaciones marca el limite con el ultimo evento anterior de esa
conversacion, independientemente del estado de entrega, y el compositor reconoce
ademas respuestas fijas de exito del backend. El limite de historial se aplica despues
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
    DoctorNotificationService -> SQLite -> DoctorNotificationDeliveryService
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
responde afirmativamente. `classify_confirmation()` interpreta marcadores de
intencion en texto normalizado y acepta cortesia alrededor de afirmaciones o
negaciones claras; señales contradictorias o inciertas siguen siendo ambiguas.
Antes de preguntar, `ConversationService` usa una lectura
del `ToolExecutor` para conservar fecha, horario y motivo de la cita en el snapshot
de la accion; esos datos se muestran sin el ID interno. Si no recupera la cita o la
lectura falla, devuelve el error publico de agenda y no guarda accion pendiente. Una
respuesta negativa o vencida no llama a una mutacion del calendario. Solo la ejecucion
confirmada puede producir un evento de cita y una notificacion al doctor.

Antes de crear una confirmacion de reprogramacion, `ConversationService` consulta la
disponibilidad del dia de destino completo. La respuesta conserva los slots ofrecidos,
el ID de la cita y el ID de llamada en el contexto por 10 minutos. Solo una seleccion
coincidente produce una accion pendiente de confirmacion; el intento de seleccionar una
hora fuera de la lista no genera una mutacion.

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
Una expresion completa de seleccion, como `agendame a las 11 am`, continua el flujo
si corresponde a la lista; una hora dentro de otra instruccion no cuenta como eleccion.
Los saludos y preguntas informativas mueven el snapshot tipado de
`conversation_workflow.py` a `paused_conversation_workflow` dentro del mismo contexto
SQLite. La transaccion conserva solo una gestion activa o pausada y el agente recibe
un recordatorio operativo independiente del historial recortado. Sus solicitudes de
mutacion se interceptan mientras responde otro tema con una gestion pausada.

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
