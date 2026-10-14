# 0052 - Solo el inicio con AM/PM en las horas de citas del paciente

## Estado

Aceptada e implementada el 14 de octubre de 2026. Extiende ADR 0051 a las citas
reservadas y sustituye sus excepciones de intervalo completo y las reglas de rangos
de ADR 0020 y ADR 0034 para la presentacion de citas al paciente.

## Contexto

Despues de simplificar la disponibilidad, el usuario solicito omitir tambien el
fin en los listados de citas y en los datos mostrados antes de cancelar una cita.
El formato debe ser coherente: `Horario: 9:00 AM` y `Hora: 9:00 AM`, en lugar de
`9:00 AM a 9:30 AM` o `09:00 - 09:30`.

## Decision

Las horas de disponibilidad, citas reservadas, detalles, opciones de identidad y
confirmaciones para el paciente presentan solo el inicio con `h:mm AM/PM`.
El destino de reprogramacion y la respuesta de reserva confirmada usan AM/PM.

El prompt solicita ese formato y la normalizacion de WhatsApp elimina el fin de
campos de hora reconocibles, incluidos listados y tablas del modelo. Los motivos
conservan sus referencias horarias. El lector del historial acepta tanto el formato
corto como los rangos antiguos, para identificar la cita que se desea modificar.

## Consecuencias

- El paciente recibe horas consistentes, sin hora de fin ni cero inicial en la hora.
- Mediodia y medianoche se presentan como `12:00 PM` y `12:00 AM`.
- Los datos estructurados y persistidos conservan inicio y fin para validar agenda
  y duracion; la confirmacion sigue vinculada a la operacion y cita exactas.
- Las notificaciones operativas al doctor conservan su contrato independiente.
