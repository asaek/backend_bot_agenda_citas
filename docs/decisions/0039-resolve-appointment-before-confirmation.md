# ADR 0039 - Resolver la cita antes de solicitar confirmacion

## Estado

Aceptada.

## Contexto

El flujo de reprogramacion podia guardar una accion pendiente y pedir confirmacion aun
cuando la lectura previa no encontrara la cita. Tras el `Si`, la mutacion fallaba con
`appointment_not_found`, aunque la pregunta no hubiera mostrado los datos de la cita.
Ademas, las excepciones de lectura se reducian silenciosamente a `None` y parecian una
cita inexistente.

## Decision

`ConversationService` solo guarda una accion pendiente cuando `ToolExecutor` recupera
la cita exacta dentro del alcance del paciente. Si no existe, devuelve
`appointment_not_found`; si la lectura falla, devuelve el error publico correspondiente
al proveedor. En ambos casos no pide confirmacion y no permite una mutacion posterior.
El modo debug puede añadir el codigo publico de agenda solo al remitente autorizado.

La misma frontera controla la primera pregunta de cancelacion. Solicitudes directas
como `quisiera cancelar la de las 10 am` se resuelven en el backend contra la agenda,
con fecha explicita o contexto del listado y una hora que conserva minutos y periodo.
Solo una coincidencia permite guardar la accion y preguntar. Referencias no coincidentes
o ambiguas se aclaran sin sustituirlas por otra cita. La pregunta textual del modelo
no crea estado ni autoriza usar una afirmacion posterior para iniciar la gestion.
El respaldo de respuesta sustituye preguntas reconocibles sin estado por una aclaracion,
y las afirmaciones aisladas no permiten al LLM reconstruir una cancelacion del historial.

## Consecuencias

- Toda confirmacion pendiente contiene una cita resuelta y sus datos visibles.
- Una lectura fallida no se confunde con una cita ausente.
- Un `Si` posterior a un error de busqueda no autoriza ni ejecuta cambios.
- La fuente de verdad y las reglas de propiedad del proveedor de calendario no cambian.
