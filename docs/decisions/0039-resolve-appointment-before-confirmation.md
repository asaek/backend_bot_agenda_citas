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

## Consecuencias

- Toda confirmacion pendiente contiene una cita resuelta y sus datos visibles.
- Una lectura fallida no se confunde con una cita ausente.
- Un `Si` posterior a un error de busqueda no autoriza ni ejecuta cambios.
- La fuente de verdad y las reglas de propiedad del proveedor de calendario no cambian.
