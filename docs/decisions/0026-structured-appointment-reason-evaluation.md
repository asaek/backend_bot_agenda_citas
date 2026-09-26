# ADR 0026 - Evaluacion estructurada del motivo de cita

## Estado

Aceptada.

## Contexto

La validacion local detecta texto vacio o evidentemente ilegible, pero no distingue
entre un sintoma visual, un seguimiento, una revision rutinaria o un motivo ajeno a
la consulta. Tambien hace falta conservar señales operativas sin convertirlas en
diagnosticos.

## Decision

Despues de la validacion local, el backend puede solicitar al LLM un objeto JSON con
esta forma controlada:

```json
{
  "quality": "valid",
  "category": "visual_symptom",
  "priority_signals": [],
  "confidence": 0.94
}
```

El backend valida los enums, exige una confianza minima de `0.75`, filtra las
señales contra una lista permitida y conserva una señal solamente si el texto del
paciente contiene evidencia compatible. Una respuesta invalida, un fallo del LLM o
una confianza insuficiente se convierte en `needs_clarification`.

El LLM no devuelve ni modifica el `reason`, no diagnostica y no ejecuta herramientas.
La autorizacion de la cita permanece en `ConversationService`, que requiere las
reglas locales, una evaluacion estructurada aceptable y la validacion normal del
`ToolExecutor`. Durante el MVP, las señales de prioridad se registran pero no
activan un triage automatico.

El estado pendiente conserva los intentos y la ultima evaluacion. Al completar una
cita, la evaluacion queda en `last_appointment_reason_evaluation` y el `reason` sigue
siendo el texto normalizado del paciente.

## Consecuencias

- La clasificacion operativa queda tipada y auditable en SQLite dentro del contexto.
- El LLM no puede inventar el motivo ni introducir diagnosticos en la agenda.
- Un fallo del evaluador puede pedir una aclaracion aunque el texto sea legible.
- La confianza y la lista de señales son reglas de backend, no instrucciones del LLM.
- La politica de urgencias clinicas sigue pendiente de una especificacion independiente.
