# Diseno - Enrutamiento de intencion con flujos pendientes

## Estado

Verificado en Raspberry Pi; evidencia en
`docs/verification/2026-10-07-conversation-pause-continuity.md`.

## Flujo

```text
Mensaje entrante
    |
    v
ConversationService carga el flujo pendiente activo
    |
    v
conversation_intent clasifica el mensaje
    |
    +-- respuesta esperada --> resolver el flujo pendiente
    +-- abandono --> limpiar estado y responder sin mutacion
    +-- ambigua --> pedir aclaracion y conservar el estado
     +-- nueva intencion --> limpiar el estado y atender la solicitud actual
     +-- pregunta informativa --> persistir pausa y atender el tema actual
     +-- retomar --> recuperar paso, revalidar vigencia y pedir confirmacion nueva
```

## Frontera de clasificacion

`ConversationService.build_reply()` consulta primero el snapshot pendiente de la
conversacion. `conversation_intent.classify_pending_interruption()` combina el tipo de
flujo (`booking_date`, disponibilidad de reserva o reprogramacion, datos de reserva o
confirmacion) con reglas normalizadas para distinguir continuacion, abandono, aclaracion
y cambio de tarea. Los saludos pausan; las peticiones de olvidar el flujo lo descartan.

La seleccion de una hora o fecha reconocida continua hacia los validadores existentes.
Despues de clasificar las interrupciones, los slots pendientes se resuelven antes
de los detectores genericos de nueva disponibilidad/fecha. Asi `elijo el horario de
las 12 del dia` no se confunde con otra reserva ni pierde la cita de origen.
Una eleccion completa compatible con la gestion activa continua aunque incluya
`agendame`. El reconocimiento exige una expresion completa de seleccion, no solo
extraer una hora de otro comando. Las preguntas informativas pausan; las preguntas
que solo expresan una eleccion incierta, como `¿11 am?`, piden aclaracion.
En una reserva se reconocen tambien `quiero/quisiera/necesito/deseo/me gustaria`
seguidos opcionalmente de un verbo de agendar y una referencia a la cita, mas la
hora. Esto evita clasificar `quisiera una cita a las 9 am` como `switch` y eliminar
la disponibilidad antes de capturar el nombre. La referencia `otra cita` no entra
en el patron de seleccion y si se reconoce como gestion nueva; una fecha adicional
tampoco se consume como eleccion del mismo dia.
El grupo compartido `_BOOKING_REQUEST_PREFIX` mantiene esos verbos alineados
entre seleccion contextual y deteccion de gestion nueva, tambien durante una pausa.
Las preguntas que comienzan consultando costo/precio se clasifican como pausa antes
de buscar una gestion nueva. Asi `Cual es el costo si deseo reservar una cita` no
descarta la reserva por contener una peticion de agenda dentro de la pregunta.

La aclaracion de reprogramacion recibe tambien el texto actual. Una seleccion
completa con hora valida usa `PendingAppointmentAvailability.matching_slots()` para
distinguir cero coincidencias de varias coincidencias AM/PM. Cero coincidencias
explica que el horario esta ocupado o no disponible; varias solicitan AM/PM.
`matching_slot()` sigue aceptando solo una coincidencia unica. La aclaracion no
borra la disponibilidad ni crea una accion pendiente de confirmacion.

Para reprogramacion, el reconocimiento completo admite verbos imperativos,
`quiero/quisiera/necesito/deseo/prefiero/me gustaria` con un verbo de cambio,
peticiones `puedes/podrias` y preferencias como `mejor`, `me sirve` o `me quedo con`.
Puede incluir una referencia a la misma cita, el horario, un saludo y cortesia.
El patron sigue anclado: no consume otra cita, una fecha adicional ni otra instruccion.
Los signos de pregunta solo se admiten como seleccion directa cuando la expresion
es una peticion cortes completa; `¿12 pm?` conserva la aclaracion tentativa.
Los signos de apertura pueden aparecer despues de un saludo o `por favor`.
Los verbos de seleccion y deteccion de gestion nueva comparten los mismos grupos
de infinitivos e imperativos, para que otra cita o fecha no conserve la gestion anterior.
`Dejar` exige una referencia directa a la cita/hora o el pronombre `la`, para no
capturar preguntas como donde dejar el coche durante la cita. `Dejarla como esta`
se reconoce primero como abandono. La cortesia despues del signo de cierre tambien
se admite en una peticion completa, manteniendo fuera las preguntas tentativas.

`parse_time_selection()` entiende mediodia y los periodos `del mediodia/del dia`.
La deteccion de solicitud sin hora destino tambien normaliza acentos y periodos,
para no reabrir la disponibilidad despues de aceptar una seleccion de mediodia.
La fecha y zona horaria siguen procediendo del snapshot persistido.

`allow_incomplete_period=True` se usa solo al clasificar y aclarar una seleccion
de reprogramacion con `a` o `p` sin la `m`. La validacion de respuesta esperada
mantiene el reconocimiento estricto: ese texto no produce accion pendiente.
La aclaracion conserva los slots y pide AM/PM completo; una correccion posterior
usa la misma transicion hacia `PendingAppointmentAction`, sin depender del LLM.
La rama de aclaracion tambien se atiende directamente desde el snapshot pausado,
sin reactivarlo ni renovar su vigencia. Una seleccion completa puede retomarlo.
La hora 12 sin periodo considera tanto 00:00 como 12:00; la coincidencia debe ser unica.

## Transiciones seguras

Un abandono o cambio de tarea limpia en una sola actualizacion los estados de fecha,
disponibilidad, motivo pendiente y accion pendiente, preservando los demas valores de
`conversations.context_json`. Despues de un cambio, el mensaje actual se procesa desde el
flujo normal; por ejemplo, una peticion para cancelar una cita genera una confirmacion
nueva y no ejecuta directamente la cancelacion.

La expresion aislada `cancela` no se trata como confirmacion ni como abandono automatico.
El backend pregunta que quiso cancelar y conserva la tarea hasta recibir una respuesta
clara. En todos los casos, el router solo dirige la conversacion: las mutaciones siguen
protegidas por sus confirmaciones existentes.

## Estado de pausa y recuperacion

`conversation_workflow.py` serializa snapshots tipados de fecha, disponibilidad,
datos de reserva o accion pendiente. `ConversationService` mueve el estado activo
a `paused_conversation_workflow` en una unica transaccion SQLite y preserva los
datos ajenos a la gestion. Las respuestas informativas pasan al agente directamente,
sin ser consumidas por los validadores de nombre, motivo o disponibilidad.

El contexto del modelo incluye un recordatorio del paso guardado, separado del
historial acotado. El callback de mutaciones del agente bloquea escrituras durante
la pausa. Solicitudes explicitas de una nueva gestion limpian el snapshot antes
de usar el flujo normal. La recuperacion explicita restaura el paso; solo fechas y
selecciones completas pueden recuperarlo implicitamente.

Los snapshots conservan su vencimiento. Si vence una reserva, se consulta el dia
nuevamente y `name_message_id` acompaña los nuevos estados de fecha/disponibilidad
para no pedir otra vez el nombre de la misma reserva. Una fecha pasada vuelve a
pedir dia. La disponibilidad actual sigue siendo autoritativa.

Una accion pausada no se consume como autorizacion. Al recuperar se vuelve a leer
la cita y, para reprogramar, se consulta el destino. Solo entonces se publica una
accion nueva con vigencia renovada. Ante errores la accion permanece pausada; si
el destino esta ocupado, se ofrecen horarios actuales antes de confirmar.
