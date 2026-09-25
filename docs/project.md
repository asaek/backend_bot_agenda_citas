# Definicion del proyecto

## Estado

Borrador.

## Objetivo

Construir progresivamente un chatbot de WhatsApp con inteligencia artificial,
entendiendo y controlando cada capa de la arquitectura desde un backend propio.
El caso de uso objetivo es gestionar citas medicas con un oftalmologo
especialista en cornea.

## Enfoque

El proyecto comenzara con la recepcion y el envio de mensajes de WhatsApp. Las
capacidades de persistencia, inteligencia artificial, memoria, herramientas y
RAG se agregaran solamente cuando la etapa anterior este comprendida y
verificada.

La primera version sera un MVP tecnico para aprendizaje y experimentacion. No
sera utilizada todavia por pacientes ni por un consultorio real.

## Usuarios del MVP tecnico

El desarrollador administrara las pruebas y utilizara varias cuentas de
WhatsApp como clientes simulados. Esto permitira observar el comportamiento del
chatbot con distintas conversaciones e identidades sin involucrar todavia a
pacientes ni clientes reales.

Cada cuenta representara un perfil de paciente de prueba. Estos perfiles podran
usar informacion ficticia o datos personales del propio desarrollador
proporcionados voluntariamente para las pruebas. No se utilizaran datos de
terceros ni de pacientes reales durante el MVP tecnico.

Cada numero de WhatsApp identificara a un solo paciente de prueba. Durante el
MVP, un paciente no podra gestionar citas para familiares u otras personas.

## Alcance actual

- Ejecutar un backend local con Python y FastAPI.
- Verificar una Callback URL con Meta.
- Recibir un evento de WhatsApp en `POST /webhook/whatsapp`.
- Parsear mensajes de texto y enviar una respuesta generada por el LLM.
- Identificar pacientes de prueba por su numero de WhatsApp.
- Guardar pacientes, conversaciones y mensajes en SQLite.
- Mantener una conversacion activa entre varias solicitudes y reinicios.
- Construir el `PatientScope` del backend con paciente, conversacion y numero de
  WhatsApp antes de cualquier operacion de agenda.
- Construir el contexto de chat desde el historial reciente y las reglas del
  asistente.
- Resolver expresiones relativas como "hoy" con el reloj y la zona horaria de la
  agenda antes de pedir al LLM una respuesta.
- Solicitar el motivo expresado por el paciente antes de crear una cita y conservar
  el horario mientras se espera ese dato.
- Mostrar los horarios libres de un dia cuando el paciente solicita agendar, incluso
  con variantes como `sacar cita`, sin indicar una hora exacta.
- Integrar el LLM en el ciclo de respuesta y conservar los fallos en SQLite.
- Verificar el ciclo integrado sin consumir APIs ni enviar mensajes reales.

## Estrategia de implementacion por cortes

El proyecto se construira y verificara una seccion a la vez. No se comenzara un
corte nuevo hasta cerrar el corte activo.

### Corte anterior: webhook y respuesta fija de WhatsApp

El corte termina cuando un mensaje enviado desde una cuenta de WhatsApp de prueba
llega a FastAPI, se parsea y recibe una respuesta fija. La verificacion real con
Meta y Raspberry Pi fue completada; las tareas historicas permanecen en
`specs/001-whatsapp-webhook/tasks.md`.

### Corte anterior: persistencia y Conversation Service

El objetivo es conservar pacientes, conversaciones y mensajes para que un segundo
mensaje del mismo numero reutilice el contexto basico despues de varias
solicitudes o de un reinicio. Las tareas de este corte estan en
`specs/002-persistence-conversation-service/tasks.md`.

### Corte verificado: ciclo integrado de LLM y WhatsApp

Los tres primeros incrementos de la etapa 4 definen una frontera independiente
del proveedor, preparan un adaptador compatible con OpenAI para Groq y
OpenRouter, construyen el contexto desde el historial reciente e integran el
ciclo de generacion y envio. Las tareas estan en
`specs/003-basic-llm-agent/tasks.md`.

### Incremento de verificacion: pruebas del ciclo sin API

El ciclo integrado se verifica con un `FakeLLMProvider`, un cliente falso de
WhatsApp y SQLite temporal. La especificacion y las tareas estan en
`specs/004-automated-webhook-tests/`.

### Corte verificado: contrato de herramientas de citas

El corte define y verifica el modelo de dominio, los inputs y outputs tipados, la
validacion previa, los errores publicos, la frontera `CalendarProvider`, un
proveedor falso determinista en memoria y `ToolExecutor`, sin conectarse a Google
Calendar. La especificacion y las tareas estan en `specs/005-tool-contract/`.

El backend de agenda ejecuta solicitudes estructuradas mediante `ToolExecutor`.
La integracion de esas solicitudes con `ConversationService` y la ejecucion del
ciclo de tool calls estan verificadas en el corte 007. Google Calendar pertenece
a un corte posterior.

### Corte verificado: contrato de tool calling del LLM

`LLMProvider` puede devolver texto o un `ToolCall` normalizado con nombre y
argumentos. Este incremento reconoce y valida la respuesta, pero todavia no
ejecuta herramientas ni permite que sus identificadores de paciente provengan
del LLM. La especificacion esta en `specs/006-llm-tool-calling/`.

### Corte verificado: orquestador del agente

El agente ejecuta el ciclo entre `LLMProvider`, `ToolExecutor` y la redaccion
final con un limite de iteraciones. El `PatientScope` se inyecta desde WhatsApp y
los resultados no exponen campos internos de paciente o calendario al LLM. Los
detalles de una cita no muestran al paciente el ID interno, aunque el agente lo
conserva para reprogramar o cancelar cuando corresponda. Las respuestas con varias
citas se entregan como listas compatibles con WhatsApp y no como tablas Markdown.
El orquestador esta en `specs/007-agent-orchestrator/`.

### Corte verificado: integracion del ToolExecutor

`main.py` crea `FakeCalendarProvider`, `BusinessHours` y `ToolExecutor` para el
runtime del MVP tecnico. `ConversationService` recibe el ejecutor y construye el
orquestador, por lo que el webhook puede ejecutar herramientas y solicitar una
redaccion final sin servicios externos. La especificacion esta en
`specs/008-tool-executor-integration/`.

### Corte verificado: adaptador de Google Calendar

El backend puede seleccionar un `GoogleCalendarProvider` sin cambiar el contrato
de herramientas. El adaptador admite OAuth o cuenta de servicio, consulta
disponibilidad mediante `freeBusy`, lista eventos paginados y administra citas de
30 minutos identificadas por propiedades privadas. Las operaciones conservan el
`PatientScope` del backend y convierten fallos externos en errores publicos. El
fake sigue siendo el valor por defecto para pruebas y desarrollo sin credenciales.
Los listados normales excluyen eventos cancelados que Google conserva como
tombstones, y las mutaciones usan `sendUpdates=all` para evitar la perdida de
eventos asociada por Google con `sendUpdates=none`.
La implementacion y las pruebas del mirror estan verificadas. La especificacion
esta en `specs/009-google-calendar-adapter/`.

### Corte verificado: persistencia de citas

La agenda conserva una identidad local separada del ID de Google. `appointments`
relaciona el ID interno, el calendario y evento externo, el paciente, el estado,
las fechas, el motivo y `last_synced_at`. `PersistentCalendarProvider` usa ese
mapa para que las herramientas reciban IDs internos y Google siga siendo la fuente
de verdad. La implementacion y la suite de Raspberry Pi estan verificadas. La
especificacion esta en `specs/010-appointment-persistence/`.

### Corte verificado: notificaciones al doctor

La funcionalidad definida en `specs/011-doctor-notifications/` envia un unico
mensaje a cada doctor configurado cuando una cita sea agendada, modificada o
cancelada correctamente. El mensaje incluye el tipo de evento, los datos de la
cita, el paciente, los ultimos 10 digitos del telefono, el resumen conversacional y
las señales de prioridad disponibles. El resumen es contenido obligatorio de esos
tres mensajes y no tiene un disparador independiente.

La frontera de eventos del corte 1 relaciona la mutacion exitosa con el mensaje
entrante y la llamada de herramienta. El corte 2 agrega la tabla
`doctor_notifications` y una bandeja local por evento y destinatario para registrar
idempotencia, estados, errores, intentos e IDs del proveedor sin bloquear la
respuesta al paciente. El corte 3 agrega un compositor que carga el historial
persistido y crea un cuerpo fijo sin diagnosticos, transcripciones completas ni IDs
internos. El corte 4 agrega la configuracion de doctores y una entrega persistente
por destinatario mediante WhatsApp, con errores aislados y reintentos de filas
fallidas. El corte 5 conecta esos servicios al webhook: la respuesta del paciente se
envia y persiste antes de intentar la notificacion, y los tres eventos completos
quedan cubiertos por pruebas de integracion junto con el webhook duplicado.
La suite local y la del mirror de Raspberry Pi pasan con 151 pruebas; la evidencia
HTTP del health check y de ambos metodos del webhook esta en
`docs/verification/2026-09-22-doctor-notifications-webhook.md`.

### Corte implementado: confirmacion de cambios de citas

La funcionalidad definida en `specs/012-appointment-change-confirmation/` exige una
confirmacion explicita antes de cancelar o reprogramar una cita. Las acciones
pendientes se conservan por conversacion durante 10 minutos; una respuesta
negativa, ambigua o vencida no modifica la agenda. Las notificaciones al doctor se
emiten solo despues de una operacion confirmada y exitosa. La pregunta muestra,
cuando la agenda puede recuperar la cita, su fecha, horario y motivo sin exponer
el ID interno; si esa consulta de lectura falla, conserva la confirmacion con el
texto generico.

### Corte implementado: motivo antes de crear una cita

La funcionalidad definida en `specs/013-appointment-reason-collection/` evita que el
LLM complete un motivo que el paciente de prueba no ha expresado. Antes de crear una
cita, el backend conserva el horario en el contexto de la conversacion y pregunta el
motivo. El siguiente mensaje del paciente completa la solicitud; solo entonces se
crea la cita y pueden emitirse las notificaciones al doctor.

### Corte implementado: disponibilidad antes de elegir la hora

La funcionalidad definida en `specs/014-date-only-availability/` consulta el dia
completo cuando el paciente pide agendar para una fecha reconocible sin indicar una
hora. El backend muestra los espacios libres, no crea una cita y espera la seleccion
del paciente. Una solicitud con hora exacta continua hacia la recoleccion del motivo.

### Fase incremental: disponibilidad real

La migracion hacia Google Calendar se realiza herramienta por herramienta. Durante
la primera fase, `CALENDAR_AVAILABILITY_PROVIDER=google` permite que
`check_availability` consulte `freeBusy` real, mientras `CALENDAR_PROVIDER=fake`
mantiene las operaciones de escritura y consulta en el proveedor determinista.
Esta configuracion es temporal para validar disponibilidad sin crear ni modificar
eventos reales.

### Cortes futuros

Los siguientes temas se especificaran por separado cuando corresponda:

1. Memoria conversacional avanzada.
2. RAG con PostgreSQL y pgvector.
3. Automatizaciones externas y despliegue.
4. Privacidad, seguridad, consentimiento y limites para informacion medica.

Esta lista expresa una direccion general y no autoriza su implementacion durante
el corte actual.

## Fuera del alcance actual

- RAG y memoria semantica.
- Integraciones con n8n.
- Redis y procesamiento mediante colas.
- PostgreSQL y pgvector.
- Despliegue de produccion.

## Flujo esperado del MVP tecnico

```text
Usuario de prueba
    |
    v
Mensaje de WhatsApp
    |
    v
Backend
    |
    v
LLM con acceso controlado a memoria y herramientas
    |
    v
Respuesta generada
    |
    v
Backend
    |
    v
Respuesta en WhatsApp
```

El MVP tecnico se considerara terminado cuando este flujo completo funcione de
extremo a extremo con las diferentes cuentas de WhatsApp utilizadas como
clientes simulados.

Cuando se confirme una operacion de agenda, el flujo podra tener una salida
adicional para el doctor:

```text
Operacion de cita confirmada
    |
    v
Notificacion a los doctores configurados
    |
    v
WhatsApp Cloud API
```

## Herramientas del MVP tecnico

El agente debera poder solicitar al backend las siguientes acciones:

- Consultar la disponibilidad de horarios.
- Crear una cita.
- Consultar las citas asociadas al paciente de prueba, con un rango opcional.
- Reprogramar una cita.
- Cancelar una cita.

El LLM podra decidir cuando solicitar una herramienta, pero el backend sera el
responsable de validar y ejecutar cada accion.

Las herramientas de agenda se integraran con Google Calendar. El LLM solicitara
la operacion correspondiente y el backend consultara o modificara el calendario;
el LLM no tendra acceso directo a Google Calendar.

## Informacion de una cita

Cada cita debera contener como minimo:

- Paciente de prueba.
- Fecha y hora.
- Duracion fija de 30 minutos durante el MVP tecnico.
- Motivo de la cita.
- ID interno disponible solo para operaciones del agente; no se muestra al paciente.
- Notas.
- Cero o mas etiquetas internas.
- Estado.

El paciente podra explicar libremente el motivo de su cita. El LLM podra
clasificar ese texto para uso interno del medico y para estadisticas. El
paciente no necesita conocer ni seleccionar esa clasificacion.

Una cita podra tener varias etiquetas internas al mismo tiempo. Las etiquetas
podran considerar, entre otros aspectos, una posible operacion, una revision
periodica, una observacion o el tipo de dolencia descrito.

Una posible urgencia se tratara como una señal de prioridad separada, no como
estado de la cita ni como diagnostico medico. Durante el MVP tecnico, esta señal
no activara un flujo especial y no impedira agendar la cita, pero debera aparecer
en el resumen de la conversacion. Antes de trabajar con pacientes reales se
debera especificar y verificar un flujo seguro de atencion para estos casos.

Los estados aceptados inicialmente son:

- `programada`
- `confirmada`
- `cancelada`
- `completada`
- `no_asistio`

## Informacion conversacional

Cuando sea necesario para completar el flujo, el sistema debera conservar:

- Nombre del paciente de prueba.
- Numero de telefono.
- Fecha preferida para la cita.
- Motivo de la cita.
- Mensajes anteriores de la conversacion, cuando existan.

La estrategia y duracion de esta memoria se definiran en una especificacion
posterior.

## Evolucion prevista

Despues de validar el MVP tecnico, el sistema evolucionara hacia la gestion de
citas medicas con un oftalmologo especialista en cornea. Antes de utilizarlo con
pacientes reales sera necesario definir requisitos de privacidad, seguridad,
consentimiento y limites para el tratamiento de informacion medica.

## Resultado general esperado

Un backend mantenible que reciba mensajes, gestione conversaciones y coordine
un agente de IA capaz de usar memoria y herramientas para asistir en la gestion
de citas.

## Preguntas abiertas

- ¿En cual de los calendarios existentes creara las citas el chatbot?
- ¿Donde se configurara el horario laboral permitido si los calendarios actuales
  no lo representan de forma explicita?
