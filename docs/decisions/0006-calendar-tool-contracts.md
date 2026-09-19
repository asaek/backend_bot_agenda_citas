# 0006 - Contratos tipados para herramientas de calendario

## Estado

Aceptada para el segundo incremento del contrato de herramientas.

## Contexto

El LLM necesita solicitar operaciones de agenda, pero sus argumentos son datos
externos no confiables. El backend debe agregar el paciente, la zona horaria,
la duracion y los calendarios configurados sin permitir que el modelo los
reemplace.

## Decision

Las cinco herramientas se describen mediante `ToolDefinition` y se convierten
desde `ToolRequest` a inputs tipados por herramienta. Las fechas se reciben en
formato ISO y se normalizan a la zona horaria predeterminada del backend.

Los inputs incluyen `PatientScope` y solo aceptan datos conversacionales:
rangos de fecha, horarios, motivos e identificadores de citas. La duracion fija
de 30 minutos, los calendarios seleccionados, la zona horaria, el usuario y la
conversacion son responsabilidad del backend.

Cada herramienta tiene un output tipado. Los errores de forma se expresan como
`DomainValidationError`; el futuro `ToolExecutor` los convertira a
`ToolResult.failure()` con un `ToolErrorCode` estable.

## Consecuencias

- El contrato no depende del formato interno de Google Calendar.
- El proveedor puede recibir valores ya normalizados y validados.
- Las definiciones pueden convertirse posteriormente al formato de tool calling
  del proveedor LLM.
- Todavia no se ejecutan operaciones ni se resuelven conflictos de agenda.

## Alternativas descartadas por ahora

- Pasar un diccionario sin contrato por cada herramienta.
- Permitir que el LLM envie duracion, calendarios o `patient_id`.
- Hacer que el proveedor de calendario interprete directamente argumentos JSON.
