# Diseno - Enrutamiento de intencion con flujos pendientes

## Estado

Verificado en Raspberry Pi.

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
```

## Frontera de clasificacion

`ConversationService.build_reply()` consulta primero el snapshot pendiente de la
conversacion. `conversation_intent.classify_pending_interruption()` combina el tipo de
flujo (`booking_date`, disponibilidad de reserva o reprogramacion, datos de reserva o
confirmacion) con reglas normalizadas para distinguir continuacion, abandono, aclaracion
y cambio de tarea. Los saludos comunes y las peticiones explicitas de olvidar lo que el
bot estaba haciendo se reconocen como cambio de intencion y se enrutan al agente.

La seleccion de una hora o fecha reconocida continua hacia los validadores existentes.
Los comandos explicitos de agenda tienen prioridad sobre un dato que podria coincidir
accidentalmente con una hora. Las preguntas nuevas se enrutan al agente y las preguntas
que parecen una respuesta, pero son inciertas, piden aclaracion sin borrar el estado.

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
