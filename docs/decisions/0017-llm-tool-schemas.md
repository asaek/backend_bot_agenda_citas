# ADR 0017 - Esquemas de herramientas en solicitudes LLM

## Estado

Aceptada.

## Contexto

El adaptador ya podia interpretar un `tool_call` devuelto por un proveedor, pero las
solicitudes reales no describian las herramientas disponibles. Como resultado, el
modelo respondia con texto y no podia solicitar `check_availability` ni las demas
operaciones de agenda.

## Decision

Enviar en cada solicitud OpenAI-compatible los cinco esquemas de herramientas
definidos por el backend y usar `tool_choice=auto`. Los esquemas describen solamente
argumentos conversacionales; no incluyen paciente, calendario, duracion ni otros
valores controlados por el backend.

Las herramientas usan `additionalProperties=false` para que el modelo no agregue
campos como clinica o calendario. El backend continua validando los argumentos y
construyendo `PatientScope` despues de recibir el `ToolCall`.

## Consecuencias

- Los modelos compatibles pueden solicitar herramientas en el flujo real, no solo
  en los fakes.
- Modelos que no soporten tool calling seguiran pudiendo devolver texto, pero no
  ejecutaran la agenda.
- Las pruebas HTTP verifican que el payload contiene los cinco esquemas.
