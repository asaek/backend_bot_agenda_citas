# 0051 - Solo la hora de inicio en listas de disponibilidad

## Estado

Aceptada e implementada el 14 de octubre de 2026. Sustituye la regla de mostrar
ambos extremos en disponibilidad de ADR 0020; su regla de 12 horas con AM/PM sigue vigente.
La excepcion para los intervalos de citas reservadas fue sustituida el mismo dia
por [ADR 0052](./0052-start-only-patient-appointment-times.md).

## Contexto

El paciente elige una cita por su hora de inicio. Mostrar tambien la hora de fin
en cada opcion alarga la lista de WhatsApp. El usuario solicito opciones como
`- 9:00 AM`, `- 9:30 AM` y `- 12:00 PM`.

## Decision

Las listas de disponibilidad para agendar y reprogramar muestran solo el inicio
de cada slot como `- h:mm AM/PM`, en la zona horaria de agenda. La regla tambien
se aplica al retomar una lista pausada y a las instrucciones del LLM.

`format_availability_reply()` y `_resumed_workflow_prompt()` siguen usando
`format_patient_time()`: sin cero inicial en la hora, con dos digitos en minutos,
`12:00 AM` para medianoche y `12:00 PM` para mediodia.

## Consecuencias

- El paciente recibe una opcion corta por linea y selecciona la hora de inicio.
- Los slots conservan inicio y fin ISO en herramientas y estado persistido para
  validar disponibilidad y duracion.
- Las listas de citas reservadas mantienen su bloque de horario y motivo con el
  intervalo completo definido en RF-708.
