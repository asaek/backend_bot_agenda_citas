# ADR 0037 - Confirmacion de citas por intencion afirmativa o negativa

## Estado

Aceptada.

Ampliada por ADR 0049: las mutaciones usan reconocimiento completo de la respuesta
respecto de la accion pendiente, sin respaldo permisivo del clasificador generico.

## Contexto

El clasificador de cambios de citas solo reconocia unas cuantas respuestas por
coincidencia exacta. Por eso `Si, por favor` se consideraba ambigua y el chatbot
repetia la solicitud de confirmacion aunque la intencion fuera clara.

## Decision

Clasificar la respuesta con marcadores de intencion sobre el texto normalizado,
aceptando expresiones afirmativas y negativas claras con palabras de cortesia o
texto adicional. Si aparecen intenciones opuestas o señales de incertidumbre, la
respuesta permanece ambigua y no autoriza ninguna mutacion.

La autorizacion sigue limitada a la accion exacta almacenada previamente. La
interpretacion permanece local y determinista; no se delega al LLM.
La etapa 1 de ADR 0049 agrega `Si es correcto` al vocabulario completo y contextualiza
la aclaracion sobre la operacion guardada. Condiciones, otras referencias y expiracion
mantienen las protecciones de esa decision.

## Consecuencias

- `Si, por favor`, `Claro, adelante` y `No, gracias` se entienden sin requerir una
  respuesta de una sola palabra.
- Una respuesta contradictoria o incierta conserva la cita y solicita aclaracion.
- Las pruebas cubren el clasificador y una reprogramacion completa con `Si, por
  favor`.
