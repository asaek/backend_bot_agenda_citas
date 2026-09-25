# 014 - Horarios libres antes de elegir una cita

## Estado

Verificado. La evidencia de ejecucion se conserva en
`docs/verification/2026-09-24-date-only-availability.md` y
`docs/verification/2026-09-25-date-only-availability-language.md`.

## Objetivo

Mostrar los espacios libres cuando el paciente solicita agendar para un dia sin
indicar una hora exacta.

## Alcance

La funcionalidad cubre:

- Deteccion de solicitudes de agenda para `hoy`, `manana`, `pasado manana` o un dia
  de la semana sin hora exacta.
- Consulta de disponibilidad para el dia completo mediante `ToolExecutor`.
- Presentacion de horarios de 30 minutos sin duplicarlos por calendario.
- Espera de la seleccion del paciente antes de iniciar la creacion.
- Conservacion del flujo existente cuando la hora ya fue indicada.

## Requisitos funcionales

### RF-1401 - Consulta de un dia sin hora

Una solicitud de agenda que contenga un dia reconocido y no contenga una hora exacta
debe consultar disponibilidad para el rango completo de ese dia.

### RF-1402 - Lista de espacios libres

La respuesta debe mostrar cada espacio libre con hora de inicio y fin, sin IDs de
calendario ni tablas Markdown.

### RF-1403 - No mutacion prematura

La consulta no debe crear, modificar ni cancelar citas y no debe preguntar el motivo
hasta que el paciente elija un horario.

### RF-1404 - Hora exacta

Una solicitud que ya contenga una hora exacta no debe ser interceptada por este flujo;
debe continuar hacia la creacion y la recoleccion obligatoria del motivo.

## Criterios de aceptacion

1. `Agendame una cita para manana` devuelve los horarios libres del dia.
2. La respuesta no invoca al LLM para decidir si debe consultar disponibilidad.
3. La respuesta no crea una cita y permite elegir un horario.
4. Un mismo horario disponible en varios calendarios se muestra una sola vez.
5. `Agendame una cita para manana a las 11:30` conserva el flujo normal.
6. Variantes equivalentes como `sacar cita` tambien consultan la disponibilidad sin
   invocar al LLM.

## Fuera del alcance

- Interpretacion de fechas arbitrarias no reconocidas por el detector.
- Seleccion automatica de un horario por parte del backend.
- Confirmacion adicional despues de que el paciente elija un horario.
