# 014 - Horarios libres antes de elegir una cita

## Estado

Verificado. El backend conserva la fecha pendiente y los horarios ofrecidos, valida la
seleccion del paciente y transfiere el flujo directamente a la recoleccion de nombre y
motivo. La evidencia de ejecucion se conserva en
`docs/verification/2026-09-24-date-only-availability.md` y
`docs/verification/2026-09-25-date-only-availability-language.md`, además de
`docs/verification/2026-09-26-backend-slot-selection.md` y
`docs/verification/2026-09-29-booking-date-and-llm-diagnostics.md`.

## Objetivo

Mostrar los espacios libres cuando el paciente solicita agendar para un dia sin
indicar una hora exacta.

## Alcance

La funcionalidad cubre:

- Deteccion de solicitudes de agenda para `hoy`, `manana`, `pasado manana` o un dia
  de la semana sin hora exacta.
- Solicitud backend de la fecha cuando el paciente expresa intencion de agendar pero
  aun no indica el dia; la respuesta posterior se interpreta en la zona horaria de agenda.
- Consulta de disponibilidad para el dia completo mediante `ToolExecutor`.
- Presentacion de horarios de 30 minutos sin duplicarlos por calendario.
- Persistencia de la fecha, slots ofrecidos y expiracion en `conversations.context_json`.
- Validacion backend de la seleccion del paciente contra los slots ofrecidos.
- Espera de la seleccion del paciente antes de iniciar la creacion.
- Transferencia directa a la solicitud controlada de nombre y motivo sin invocar al LLM.
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

Una solicitud inicial que ya contenga una hora exacta no debe ser interceptada por este flujo;
debe continuar hacia la creacion y la recoleccion obligatoria del motivo.

### RF-1405 - Seleccion controlada

Despues de mostrar horarios, el backend debe conservar la fecha y los slots ofrecidos
en `conversations.context_json` durante 10 minutos. Una hora expresada por el paciente
solo es valida si coincide con uno de esos slots. Una seleccion valida debe crear el
estado pendiente de la cita y continuar con las preguntas fijas de nombre y motivo sin
consultar al LLM. Una seleccion invalida debe conservar los slots y pedir que elija uno
de la lista.

### RF-1406 - Fecha como continuacion de una reserva

Cuando un mensaje reconocible pide agendar sin indicar el dia ni una hora exacta, el
backend debe guardar una solicitud pendiente durante 10 minutos y preguntar que dia
desea reservar. Una respuesta relativa como `hoy` o `mañana` debe consultarse mediante
`check_availability` sin volver a depender del LLM para conservar la intencion.

## Criterios de aceptacion

1. `Agendame una cita para manana` devuelve los horarios libres del dia.
2. La respuesta no invoca al LLM para decidir si debe consultar disponibilidad.
3. La respuesta no crea una cita y permite elegir un horario.
4. Un mismo horario disponible en varios calendarios se muestra una sola vez.
5. `Agendame una cita para manana a las 11:30` conserva el flujo normal.
6. Variantes equivalentes como `sacar cita` tambien consultan la disponibilidad sin
   invocar al LLM.
7. `Hola quisiera agendar una cita para el lunes`, `damela a las 10 am` y `Siento rara
   la vista` solicitan el motivo una sola vez y crean una sola cita con ese texto.
8. La seleccion valida no invoca al LLM, conserva el estado entre mensajes y elimina el
   estado de disponibilidad despues de iniciar la recoleccion de datos.
9. Una hora no ofrecida, una solicitud sin hora o una disponibilidad vencida no crea la
   cita ni pierde los controles del backend.
10. `Quisiera agendar una` seguido de `hoy` consulta y muestra los horarios disponibles
    sin invocar al LLM en ninguno de esos dos turnos.

## Fuera del alcance

- Interpretacion de fechas arbitrarias no reconocidas por el detector.
- Confirmacion adicional despues de que el paciente elija un horario.
