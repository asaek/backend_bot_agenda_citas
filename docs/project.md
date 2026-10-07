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
- Solicitar, validar y evaluar estructuradamente el motivo expresado por el paciente
  antes de crear una cita; conservar el horario y metadata mientras se espera ese
  dato.
- Solicitar y persistir el nombre del paciente cuando aun no este registrado antes
  de continuar con el motivo.
- Separar señales operativas de prioridad de cualquier diagnostico y conservarlas sin
  cambiar el flujo de agendamiento.
- Detectar ojos rojos como señal operativa y llevarla a la notificacion mediante el
  catalogo seguro, sin permitir señales de texto libre del LLM.
- Mostrar los horarios libres de un dia cuando el paciente solicita agendar, incluso
  con variantes como `sacar cita`, sin indicar una hora exacta.
- Conservar durante 10 minutos la intencion de agendar sin hora exacta mientras se
  espera el dia y resolver respuestas como `hoy` directamente en el backend.
- Persistir la disponibilidad ofrecida y validar en el backend la hora elegida antes
  de iniciar la recoleccion de nombre y motivo.
- Consultar y mostrar los horarios libres del dia destino antes de confirmar una
  reprogramacion, y aceptar solo una seleccion de esa lista.
- Mostrar la disponibilidad del dia de una cita identificada antes de preguntar por una
  hora destino para reprogramarla.
- Clasificar la intencion nueva antes de continuar un flujo pendiente, permitiendo
  abandonarlo o cambiar de tarea sin mutaciones accidentales.
- Integrar el LLM en el ciclo de respuesta y conservar en SQLite el tipo de fallo y,
  cuando exista, el codigo HTTP del proveedor sin copiar contenido sensible al log.
- Alternar entre Groq y OpenAI mediante `LLM_PROVIDER`, con credenciales y modelos
  preconfigurados por proveedor y sin cambiar el flujo conversacional.
- Usar Responses API para OpenAI y Chat Completions para Groq/OpenRouter con un
  contrato compartido de respuestas y llamadas a herramientas.
- Habilitar un modo debug apagado por defecto que muestre diagnosticos seguros solo a
  remitentes de WhatsApp explicitamente autorizados.
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
del proveedor, preparan un adaptador compatible con OpenAI para Groq, OpenAI y
OpenRouter, construyen el contexto desde el historial reciente e integran el
ciclo de generacion y envio. `LLM_PROVIDER` permite cambiar entre Groq y OpenAI
sin editar sus claves ni modelos, siempre que ambas configuraciones esten
preparadas en `.env`. Las tareas estan en
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
30 minutos. Las citas creadas por el bot se identifican por propiedades privadas;
las ingresadas por el medico o secretaria se asocian por una linea exacta con el
numero E.164 de WhatsApp en la descripcion. Las operaciones conservan el
`PatientScope` del backend y convierten fallos externos en errores publicos. El
fake sigue siendo el valor por defecto para pruebas y desarrollo sin credenciales.
Los listados normales excluyen eventos cancelados que Google conserva como
tombstones, y las mutaciones usan `sendUpdates=all` para evitar la perdida de
eventos asociada por Google con `sendUpdates=none`.
Un evento manual sin esa linea no se muestra ni se modifica desde el bot; los eventos
manuales existentes requieren una actualizacion unica de su descripcion.
La implementacion y las pruebas del mirror estan verificadas. La especificacion
esta en `specs/009-google-calendar-adapter/`.
La extension para citas manuales tambien esta cubierta por una regresion y la suite
completa verificada en Raspberry Pi. La verificacion con un calendario real requiere
credenciales externas.

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

### Corte verificado: confirmacion de cambios de citas

La funcionalidad definida en `specs/012-appointment-change-confirmation/` exige una
confirmacion explicita antes de cancelar o reprogramar una cita. Las acciones
pendientes se conservan por conversacion durante 10 minutos; una respuesta
negativa, ambigua o vencida no modifica la agenda. La interpretacion acepta
respuestas naturales claras como `Si, por favor` y `Claro`, y vuelve a preguntar
ante respuestas contradictorias o inciertas. Las notificaciones al doctor se emiten
solo despues de una operacion confirmada y exitosa. La pregunta muestra la fecha,
horario y motivo recuperados sin exponer el ID interno. Si no se encuentra la cita o
falla la lectura de agenda, no crea una confirmacion pendiente ni permite ejecutar la
mutacion.

### Corte implementado: motivo antes de crear una cita

La funcionalidad definida en `specs/013-appointment-reason-collection/` evita que el
LLM complete un motivo que el paciente de prueba no ha expresado. Antes de crear una
cita, el backend siempre solicita el nombre completo, incluso si ya estaba registrado,
lo actualiza en `patients.name` y despues pregunta el motivo. El horario y el estado
pendiente se conservan en el contexto de la conversacion. El validador local rechaza entradas
evidentemente ilegibles sin perder ese estado. Un evaluador estructurado clasifica la
calidad, categoria y señales permitidas; el backend conserva los intentos y la fecha,
pero mantiene el texto del paciente como unico motivo. Solo una evaluacion aceptable
completa la solicitud y permite crear la cita y emitir las notificaciones al doctor.

Las referencias vagas como `Lo de siempre` piden aclaracion. Las señales de prioridad
se limitan a codigos evidenciados por el texto y se convierten en descripciones
operativas sin nombres de enfermedades antes de incluirse en una notificacion
interna. Este comportamiento es solo tecnico: falta una politica clinica explicita
antes de usarlo con pacientes reales.

### Corte implementado: disponibilidad antes de elegir la hora

La funcionalidad definida en `specs/014-date-only-availability/` consulta el dia
completo cuando el paciente pide agendar para una fecha reconocible sin indicar una
hora. El backend muestra los espacios libres, conserva la fecha y los slots en la
conversacion y valida la seleccion del paciente antes de iniciar la recoleccion de
nombre y motivo. Si primero falta el dia y no se indico una hora exacta, conserva la
solicitud y procesa una respuesta relativa posterior, como `hoy`, sin depender del LLM.
Una solicitud con hora exacta continua hacia la recoleccion del motivo.

### Corte verificado: diagnostico seguro durante depuracion

La funcionalidad definida en `specs/015-debug-error-reporting/` permite mostrar el
proveedor, el tipo de error y el codigo HTTP en la respuesta al paciente de prueba solo
cuando `DEBUG_MODE` esta activo y su numero aparece en `DEBUG_WHATSAPP_NUMBERS`. El modo
puede mostrar tambien codigos publicos de agenda. Permanece desactivado por defecto y
nunca expone excepciones crudas, prompts, mensajes, cuerpos HTTP ni credenciales.

### Corte verificado: enrutamiento de intencion con flujos pendientes

La funcionalidad definida en `specs/016-conversation-intent-routing/` permite que el
mensaje mas reciente del paciente abandone o reemplace una seleccion, una reserva
pendiente o una confirmacion. Las expresiones ambiguas solicitan aclaracion y no alteran
el calendario. Las confirmaciones descartadas no pueden reutilizarse posteriormente.

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
- Consultar las citas asociadas al paciente de prueba, con un rango opcional; los
  extremos omitidos o ambos valores `null` representan una consulta sin rango.
- Presentar cada cita listada en WhatsApp con horario y motivo de consulta en un
  bloque de varias lineas, con las etiquetas en negrita compatible con WhatsApp y
  el motivo debajo de su etiqueta.
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
