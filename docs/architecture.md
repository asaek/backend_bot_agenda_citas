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

### Conversation Service

Identifica al paciente de prueba por su numero de WhatsApp, busca o crea una
conversacion activa y construye un `PatientScope` con el paciente, la
conversacion y el numero de WhatsApp resueltos por el backend. Conserva el
historial y construye el contexto para el LLM. El `PatientScope` no se obtiene
de los argumentos del LLM.
El contexto comienza con las reglas del asistente y usa los mensajes mas
recientes persistidos. Las reglas indican que los detalles de una cita no deben
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
Las solicitudes con hora exacta continúan por el flujo normal.

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
La suite verifica esta frontera sin Google Calendar.

### Persistence y repositories

`persistence.py` administra conexiones, esquema y transacciones SQLite.
`repositories.py` encapsula las operaciones de pacientes, conversaciones y
mensajes y citas. La ruta de la base se configura mediante `DATABASE_PATH`.
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
conversacional y las señales de prioridad disponibles. Ese cuerpo se entregara a
cada doctor configurado.
El resumen sera contenido de cada notificacion y no un disparador independiente.

La composicion usa `generate_text()` con un prompt interno sin herramientas. El
resultado del LLM se valida y se limita; los diagnosticos, recomendaciones,
transcripciones completas y valores internos conocidos se descartan o sustituyen
por contenido seguro antes de formar el cuerpo.

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

`main.py` recolecta los eventos durante `ConversationService.build_reply()`. Despues
de enviar y persistir la respuesta del paciente, compone el resumen y llama a
`DoctorNotificationDeliveryService` por cada evento. La entrega al doctor se
encapsula en un limite de errores: una falla de configuracion, composicion,
persistencia o WhatsApp se registra sin propagarse al paciente; el servicio de
entrega mantiene ademas el aislamiento entre destinatarios.

### Confirmacion de cambios de citas

La funcionalidad definida en `specs/012-appointment-change-confirmation/` intercepta
las solicitudes de cancelacion y reprogramacion antes de `ToolExecutor`. La accion
exacta queda pendiente en `conversations.context_json` hasta que el paciente
responde afirmativamente. Antes de preguntar, `ConversationService` usa una lectura
del `ToolExecutor` para conservar fecha, horario y motivo de la cita en el snapshot
de la accion; esos datos se muestran sin el ID interno. Una respuesta negativa o
vencida no llama a una mutacion del calendario. Solo la ejecucion confirmada puede
producir un evento de cita y una notificacion al doctor.

### Motivo antes de crear una cita

La funcionalidad definida en `specs/013-appointment-reason-collection/` intercepta
`create_appointment` antes de `ToolExecutor`. `ConversationService` guarda el
horario en `conversations.context_json`, pregunta el motivo y descarta el valor que
el LLM haya propuesto. El siguiente mensaje no vacio del paciente se normaliza solo
en espacios y se usa como `reason` para ejecutar la cita.

La primera pregunta no modifica la agenda ni genera eventos. Una creacion exitosa
posterior conserva el mismo flujo de respuesta, persistencia y notificacion al
doctor; una solicitud vencida despues de 10 minutos se limpia sin tocar el
proveedor.

### LLMProvider y agente LLM basico

Define el contrato asincrono `generate(messages)` para que el agente basico y la
logica conversacional no dependan de un proveedor concreto. El adaptador
`OpenAICompatibleLLMProvider` usa `httpx` y variables de entorno para Groq u
OpenRouter. Cada solicitud incluye los cinco esquemas OpenAI-compatible de las
herramientas; el proveedor puede devolver texto o un `ToolCall` estructurado.

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
usa listas en lugar de tablas Markdown. El limite de iteraciones se configura
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
administradas por el chatbot; el adaptador solo puede listarlos de forma indirecta
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
Los eventos creados por el chatbot llevan propiedades extendidas privadas para
identificarlos como citas administradas por el sistema. Las operaciones de lectura
y modificacion exigen `managed_by=whatsapp_chatbot` y el `patient_id` del alcance
actual; los eventos existentes sin esos metadatos no se reinterpretan ni se
modifican.

La herramienta `list_appointments` entrega a la capa conversacional las citas
administradas del paciente, incluyendo su ID interno para futuras operaciones de
reprogramacion o cancelacion. El serializador del agente omite el calendario y el
`PatientScope` antes de devolver el resultado al LLM.

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
