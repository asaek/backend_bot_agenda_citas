# 0008 - Errores publicos para las herramientas de agenda

## Estado

Aceptada para el incremento de errores publicos del contrato de herramientas.

## Contexto

Las validaciones locales y los proveedores de calendario tienen excepciones
distintas. Exponerlas al agente acoplaria el contrato al proveedor, filtraria
detalles internos y haria que el LLM tuviera que interpretar fallos de una API
externa.

## Decision

El backend define ocho errores propios: `InvalidToolArguments`, `SlotUnavailable`,
`OutsideBusinessHours`, `AppointmentNotFound`, `AppointmentAccessDenied`,
`InvalidAppointmentState`, `CalendarProviderUnavailable` y
`CalendarProviderError`.

`tool_results.py` convierte excepciones locales, de validacion o de un proveedor
en `ToolResult.failure()` mediante un codigo y un mensaje estable. Los fallos
transitorios reconocibles se convierten en `CalendarProviderUnavailable` y los
demas fallos externos en `CalendarProviderError`. El mensaje de la excepcion
original nunca se copia al resultado publico.

Los adaptadores concretos pueden conservar la excepcion original como causa para
logs internos, pero deben lanzar un error publico o delegar la operacion en
`execute_with_public_errors` antes de devolver el resultado al agente.

## Consecuencias

- El LLM recibe un contrato independiente de Google Calendar.
- Los mensajes para el agente son entendibles y no revelan respuestas internas.
- Los errores transitorios pueden marcarse como reintentables.
- Los logs internos y la politica de observabilidad quedan fuera de este contrato.

## Alternativas descartadas

- Propagar directamente excepciones de Google al flujo del agente.
- Devolver `str(error)` como mensaje de `ToolError`.
- Crear una jerarquia publica con tipos especificos de Google Calendar.
