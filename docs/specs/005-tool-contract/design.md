# Diseno - Modelo de dominio del contrato de herramientas

## Estado

Implementado para el incremento del ejecutor del contrato.

## Frontera del dominio

```text
Contexto de WhatsApp
    |
    v
PatientScope creado por el backend
    |
    v
ToolRequest + argumentos conversacionales
    |
    v
ToolExecutor
    |
    v
CalendarProvider
    +-- FakeCalendarProvider
    +-- Google Calendar (futuro)
    |
    v
ToolResult
```

El modulo `calendar_domain.py` no realiza red, no conoce FastAPI, no consulta
SQLite y no permite que el LLM seleccione el paciente o los calendarios.

## Tipos principales

`Appointment` y `AvailableSlot` validan intervalos con fechas conscientes de zona
horaria y una duracion fija de 30 minutos. `Appointment` tambien expone si su
estado permite reprogramacion.

`PatientScope` representa la identidad ya resuelta por el webhook. Contiene los
identificadores internos del paciente y la conversacion junto con el numero de
WhatsApp recibido.

`ToolRequest` combina un `ToolName`, argumentos no confiables provenientes del
flujo conversacional y el `PatientScope` confiable. Rechaza campos reservados
como `patient_id`, `patient_scope`, `calendar_id` y `calendar_ids`.

`ToolResult` usa `ToolError` y `ToolErrorCode` para que el ejecutor pueda devolver
errores seguros y estables sin exponer excepciones del proveedor.

Las excepciones publicas se definen en `calendar_domain.py` y se reexportan desde
`calendar_errors.py`. Cada una tiene un codigo, un mensaje estable y una marca de
reintento. Las excepciones de proveedor no deben formar parte de este contrato.

## Contratos por herramienta

`tool_contracts.py` registra las definiciones publicas y convierte el
`ToolRequest` generico en un input tipado:

- `CheckAvailabilityInput` recibe un rango y produce `CheckAvailabilityOutput`
  con espacios de 30 minutos.
- `CreateAppointmentInput` recibe el inicio y el motivo, y produce
  `CreateAppointmentOutput`.
- `ListAppointmentsInput` recibe un rango opcional completo y produce
  `ListAppointmentsOutput`.
- `RescheduleAppointmentInput` recibe el identificador y el nuevo inicio, y
  produce `RescheduleAppointmentOutput`.
- `CancelAppointmentInput` recibe el identificador y produce
  `CancelAppointmentOutput`.

La funcion `parse_tool_request()` valida nombres obligatorios y desconocidos,
normaliza fechas ISO a la zona horaria predeterminada y conserva el
`PatientScope` creado por el backend. No agrega duracion ni calendarios a los
argumentos del LLM.

## Validacion previa

`tool_validation.py` contiene `BusinessHours`, `TimeWindow` y
`validate_tool_input()`. La funcion no realiza llamadas de red. Recibe las citas
existentes como una fotografia ya disponible para comprobar solapamientos y
excluye estados que ya no bloquean el horario.

`ToolValidationError` conserva un `ToolErrorCode`, por ejemplo
`DATE_IN_PAST`, `OUTSIDE_BUSINESS_HOURS`, `SLOT_UNAVAILABLE`,
`APPOINTMENT_ACCESS_DENIED` o `INVALID_APPOINTMENT_STATE`. El `ToolExecutor`
reutiliza la conversion publica antes de devolverlos al agente.

`tool_results.py` contiene la frontera de conversion. `public_error_from_exception`
reduce errores de validacion a errores propios, clasifica fallos transitorios
conocibles como `CalendarProviderUnavailable` y reduce cualquier otro fallo
externo a `CalendarProviderError`. `execute_with_public_errors` aplica la misma
regla a una operacion asincrona y solo devuelve `ToolResult`, por lo que el LLM
no recibe la excepcion original ni sus detalles.

`fake_calendar_provider.py` implementa `CalendarProvider` en memoria. Mantiene
periodos ocupados y citas en colecciones privadas, ordena las respuestas por
fecha e identificador y genera identificadores secuenciales. Para crear una cita
elige el primer calendario configurado que no tenga un periodo ocupado ni una
cita activa. Reprogramar conserva el calendario y el identificador; cancelar
conserva la cita y cambia su estado a `cancelled`.

Los errores se pueden configurar por `ToolName` como persistentes o de una sola
ejecucion. Esto permite probar tanto conflictos reales del fake como fallos del
proveedor a traves de `execute_with_public_errors`.

## ToolExecutor

`tool_executor.py` recibe un `CalendarProvider`, `BusinessHours`, la zona horaria
del backend y un reloj opcional para pruebas. `execute()` valida el tipo
`ToolRequest`, llama a `parse_tool_request()` y aplica primero las reglas que no
requieren red. Para crear o modificar obtiene despues una fotografia de las citas
del `PatientScope` desde `list_appointments()` y repite la validacion de conflictos,
pertenencia y estado con esa fotografia.

La ejecucion se despacha por tipo de input y construye exactamente uno de los
cinco outputs tipados. El calendario no se copia desde los argumentos: el fake lo
elige de su configuracion y un proveedor real hara lo mismo. Cualquier
`Exception` se reduce con `tool_result_from_exception()`, por lo que el llamador
recibe un `ToolResult` tanto en exito como en fallo.

## CalendarProvider

El protocolo asincrono declara:

- `check_availability`
- `create_appointment`
- `list_appointments`
- `reschedule_appointment`
- `cancel_appointment`

Los calendarios seleccionados se configuran al construir el proveedor. No son
argumentos de los metodos ni del LLM. La validacion de negocio y la traduccion de
errores pertenecen al ejecutor. La conversion publica ya esta aislada en
`tool_results.py` para que el ejecutor no tenga que conocer excepciones de Google.

## Limite con el LLM

El contrato actual de `LLMProvider` devuelve texto mediante `generate(messages)`.
Este incremento define la frontera de dominio de las herramientas, pero no
agrega todavia el formato de tool calling del proveedor LLM. La integracion se
implementara despues de probar el ejecutor con solicitudes estructuradas.
