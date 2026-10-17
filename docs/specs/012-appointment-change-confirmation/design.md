# Diseno - Confirmacion de cambios de citas

## Estado

Verificado en Raspberry Pi. La confirmacion se aplica antes de ejecutar el proveedor de calendario y
conserva la integracion de eventos y notificaciones existente.

## Flujo implementado

```text
Mensaje del paciente
    |
    v
ConversationService
    |
    +-- accion pendiente existente --> clasificar Si/No/ambiguedad y vigencia
    |                                  +-- Si -> ejecutar la accion exacta
    |                                  +-- No/vencida -> descartar sin mutacion
    |                                  +-- ambigua -> pedir aclaracion
    |
    +-- cancelacion directa --> leer agenda y resolver una cita exacta
    |                            +-- ambigua/no coincide -> pedir dia/horario
    |                            +-- resuelta -> guardar accion y pedir Si/No
    |
    v
AgentOrchestrator
    |
    +-- cancel -> resolver cita en alcance y guardar accion antes de preguntar
    |
    +-- reschedule -> resolver cita en alcance
     |                        |-- ausente/fallo -> error publico, sin estado pendiente
     |                        +-- encontrada -> consultar disponibilidad del dia destino
     |                                             |
     |                                             +-- mostrar slots y esperar seleccion
     |                                                   |
     |                                                   +-- guardar accion exacta y pedir Si/No
     |                                                         sin modificar el calendario
    |
    +-- confirmacion afirmativa -> ToolExecutor -> CalendarProvider
                                             |
                                             v
                                  evento y notificacion al doctor
```

## Frontera de confirmacion

`AgentOrchestrator` recibe un manejador previo a la ejecucion de herramientas.
`ConversationService` intercepta solo `cancel_appointment` y
`reschedule_appointment` y valida la forma basica de sus argumentos. Antes de persistir
la accion o construir la pregunta, obtiene mediante `ToolExecutor` una cita del alcance
del paciente. Si el ID no aparece, devuelve `appointment_not_found`; si falla la lectura,
normaliza la excepcion a su error publico de agenda. En ambos casos termina el turno sin
accion pendiente, confirmacion ni mutacion. Solo una cita recuperada permite mostrar
fecha, horario y motivo y guardar la operacion exacta.
`PendingAppointmentAction._format_appointment_details()` muestra solo el inicio
mediante `format_patient_time()`, como `Hora: 9:00 AM`. `_format_requested_start()`
usa tambien AM/PM para el destino de reprogramacion. Los candidatos de
`_format_appointment_target_selection()` muestran fecha y solo la hora de inicio.
Los datos persistidos siguen conservando inicio y fin ISO; ADR 0052 registra la
regla de presentacion.

La accion pendiente conserva el nombre de la herramienta, sus argumentos permitidos,
el ID de la llamada, los tiempos de creacion y expiracion y los datos recuperados de la
cita. Se almacena dentro de `conversations.context_json`, preservando cualquier otro
contexto existente. No existe una accion pendiente si la consulta no recupera una cita.

## Inicio backend de la cancelacion

`conversation_intent.is_cancellation_request()` identifica una solicitud directa,
incluida una referencia a `la de las 10 am` sin repetir la palabra cita. Se atiende
antes del agente en `ConversationService._resolve_cancellation_request()`.
El backend consulta `list_appointments` en el alcance del paciente, aplica la fecha
explicita o el contexto del listado y filtra la hora con minutos y periodo AM/PM.
Usa `normalize_time_selection_punctuation()` y `has_explicit_time_period()` para
conservar el significado temporal. Fechas numericas invalidas, datos temporales
numericos no interpretados o varios objetivos no se reducen a la primera cita disponible.

`_request_appointment_confirmation()` recupera la cita seleccionada y guarda el
`PendingAppointmentAction` antes de devolver la pregunta canonica con fecha, hora
y motivo. El LLM no decide esa pregunta para una solicitud reconocida. Un error
de lectura devuelve su respuesta publica; cero o varias candidatas reciben una
aclaracion de identidad sin accion pendiente. El formato de candidatos se comparte
con reprogramacion, conservando la operacion solicitada en el texto.

Como respaldo, una pregunta textual reconocible de confirmacion de cancelacion
del agente sin accion pendiente se sustituye por la solicitud de dia/horario.
Durante una pausa, ese respaldo solicita retomar antes de confirmar. Una llamada
de cancelacion propuesta por el LLM en respuesta a una afirmacion aislada se bloquea:
el historial no crea ni reactiva una accion que el backend no tiene guardada.

Cuando el paciente solicita cambiar la hora sin dar un destino, `ConversationService`
recupera las citas vigentes y resuelve la referencia usando primero la lista de citas
recientemente mostrada y la hora mencionada. Si queda una unica cita, consulta de
inmediato todos los horarios disponibles de su fecha, sin pedir primero una hora libre.
Si la referencia sigue ambigua, muestra las citas candidatas y pregunta cual quiere
cambiar; no modifica ninguna.

Para una reprogramacion, `ConversationService` consulta `check_availability` para el dia
local de `new_start_at` (o el dia de la cita si el paciente solo solicita cambiar la
hora). `PendingAppointmentAvailability` conserva los slots ofrecidos junto con el ID de
la cita y la llamada de origen durante 10 minutos. Una seleccion valida vuelve a resolver
la cita y crea la accion de reprogramacion con el inicio elegido; una seleccion que no
coincide con la lista solo pide elegir un horario ofrecido. La confirmacion vinculada a
esa accion es la unica que puede ejecutar la mutacion.

## Resolucion

En el siguiente mensaje, `ConversationService` usa `classify_action_confirmation()`
con la herramienta pendiente antes del router generico y tambien al resolver la accion.
Reconoce respuestas completas normalizadas, con cortesia, como `Si cancelala`,
`Cancela la cita por favor`, `Si, por favor` o `No, gracias`. Una fecha, hora, otra
cita o instruccion adicional queda fuera del reconocimiento. `None` deja ese texto
al router; `UNKNOWN` conserva la accion y pide aclaracion. No existe un respaldo
permisivo por encontrar `Si` dentro de cualquier texto adicional.
La frase `es correcto` forma parte del vocabulario, por lo que `Si es correcto`
supera el reconocimiento completo. `Si esta bien` y `Correcto, por favor` mantienen
la misma ruta determinista. Antes de quitar acentos, un `si` posterior a otra clausula
en una respuesta afirmativa se conserva como posible condicion y devuelve `UNKNOWN`;
las preguntas informativas siguen al router y un `sí` explicito no se
confunde con ese conector. Asi `Si, si esta bien` no autoriza la accion aunque sus
palabras individuales esten permitidas.
Si encuentra señales contradictorias o de incertidumbre, conserva la
accion y pide aclaracion. Una afirmacion reconstruye la llamada almacenada y la
ejecuta mediante `AgentOrchestrator.execute_confirmed_tool()`; una respuesta
negativa limpia el estado sin tocar el calendario. `unchanged_reply()` comunica
que la cita sigue agendada usando la fecha y hora original del snapshot.
`PendingAppointmentAction.clarification_prompt(now=...)` construye una aclaracion
desde ese mismo snapshot: fecha/hora original, operacion y destino de reprogramacion.
Usa el reloj y zona de agenda para `hoy` y AM/PM. Tanto la aclaracion del router
como la resolucion desconocida usan ese metodo; no consultan al LLM, no cambian
argumentos ni renuevan `expires_at`. Si el destino cambia de dia, incluye su fecha.

Antes de esta resolucion, el router transversal de
`specs/016-conversation-intent-routing/` permite descartar una confirmacion si el paciente
cambia explicitamente de tarea. La nueva solicitud se atiende sin dejar una mutacion
antigua esperando un `Si` posterior.
Las respuestas contextuales durante una pausa solo piden retomar y no restauran
una autorizacion antigua. `cancela` aislado durante una cancelacion activa conserva
la accion y pregunta unicamente si desea cancelar esa misma cita.

La confirmacion expira a los 10 minutos. El estado se limpia antes de una ejecucion
confirmada para evitar reutilizar la misma autorizacion.

## Integracion con notificaciones

Despues de una mutacion exitosa, `_appointment_result_reply()` responde al paciente
con los datos definitivos de la cita y el nombre persistido usando los bloques
compartidos de spec 020. Este mensaje de resultado es posterior a la pregunta de
confirmacion y no constituye una autorizacion para otra mutacion.

La consulta inicial de disponibilidad y la seleccion del horario no emiten un
`AppointmentNotificationEvent`. La confirmacion muestra los datos publicables de la cita
y el horario destino sin el ID interno. El evento se crea unicamente cuando la operacion
confirmada devuelve un resultado exitoso, por lo que el flujo existente de entrega al
doctor permanece aislado y con idempotencia.
