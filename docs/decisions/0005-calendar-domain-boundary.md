# 0005 - Frontera del dominio de citas y herramientas

## Estado

Aceptada para el primer incremento del contrato de herramientas.

## Contexto

El agente necesitara consultar y modificar una agenda, pero no debe permitir que
el LLM decida directamente el paciente, los calendarios o las reglas de negocio.
Ademas, las pruebas deben poder ejecutarse antes de integrar Google Calendar.

## Decision

Se define un modelo de dominio independiente en `calendar_domain.py` con citas,
espacios, alcance de paciente, solicitudes, resultados y un protocolo asincrono
`CalendarProvider`.

Las citas y los espacios duran 30 minutos y todas sus fechas deben incluir una
zona horaria. El backend crea `PatientScope` desde el contexto de WhatsApp. Los
calendarios se seleccionan mediante configuracion del backend. El LLM solo puede
proporcionar argumentos conversacionales no reservados.

La ejecucion se separara del modelo mediante un `ToolExecutor` y un proveedor
falso antes de implementar el adaptador de Google.

## Consecuencias

- Las reglas de dominio pueden probarse sin red ni credenciales.
- Las implementaciones de calendario pueden cambiar sin cambiar el agente.
- El LLM no controla el alcance del paciente ni los calendarios.
- El modelo todavia no persiste citas ni ejecuta operaciones externas.

## Alternativas descartadas por ahora

- Permitir `patient_id` y `calendar_id` en los argumentos del LLM.
- Integrar Google Calendar directamente en `main.py`.
- Usar texto libre como unico contrato entre el agente y el calendario.
