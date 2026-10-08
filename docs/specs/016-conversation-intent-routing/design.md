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
Una eleccion completa compatible con la gestion activa continua aunque incluya
`agendame`. El reconocimiento exige una expresion completa de seleccion, no solo
extraer una hora de otro comando. Las preguntas informativas pausan; las preguntas
que solo expresan una eleccion incierta, como `¿11 am?`, piden aclaracion.

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
