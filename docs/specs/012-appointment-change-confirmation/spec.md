# 012 - Confirmacion de cambios destructivos de citas

## Estado

Verificado en Raspberry Pi. La cancelacion y la reprogramacion requieren una confirmacion explicita
antes de modificar la fuente de verdad de agenda; la cita debe resolverse antes de pedir
confirmacion. Para reprogramar, el backend consulta y presenta los horarios libres del dia
destino incluso si el paciente aun no propone una hora, y solicita elegir uno antes de
pedir confirmacion. La evidencia del inicio de reprogramacion sin hora esta en
`docs/verification/2026-10-05-reschedule-before-time-selection.md`. La clasificacion acepta
expresiones naturales claras y conserva la aclaracion para respuestas contradictorias o
inciertas. El enrutamiento de intenciones nuevas y abandono durante una confirmacion se
define en `specs/016-conversation-intent-routing/`.

## Objetivo

Evitar que una solicitud ambigua, un error del LLM o una interpretacion incorrecta
cancele o modifique una cita sin que el paciente confirme la operacion exacta.

## Alcance

La funcionalidad cubre:

- Confirmacion previa para cancelar una cita.
- Confirmacion previa para reprogramar una cita a un horario concreto.
- Consulta y presentacion de los horarios libres de todo el dia destino antes de confirmar
  una reprogramacion.
- Presentacion de los horarios libres antes de preguntar una hora preferida cuando el
  paciente solicita cambiar solo la hora de una cita existente.
- Seleccion de un horario ofrecido y validacion de esa seleccion antes de crear la
  confirmacion pendiente.
- Respuesta negativa sin cambios en la agenda.
- Expiracion de una confirmacion pendiente despues de 10 minutos.
- Emision de notificaciones al doctor solamente despues de la operacion confirmada.

La creacion de una cita no requiere esta confirmacion dentro de este alcance.

## Requisitos funcionales

### RF-1201 - Confirmacion previa

Una solicitud de `cancel_appointment` o `reschedule_appointment` no debe ejecutar
la mutacion del proveedor de calendario hasta recibir una confirmacion afirmativa
del paciente. Antes de formular la pregunta, el backend debe resolver la cita dentro
del alcance del paciente. Si no existe, debe devolver el error publico correspondiente
sin guardar una accion pendiente. Si la lectura falla, debe devolver el error publico
del proveedor sin presentar una confirmacion.

### RF-1202 - Operacion exacta

La confirmacion debe estar vinculada a una sola operacion, cita y horario nuevo
cuando corresponda. Una confirmacion no puede autorizar otra mutacion distinta.

La pregunta de confirmacion debe mostrar los datos de la cita que se modificara:
fecha, horario y motivo. No debe mostrar el ID interno de la cita.

### RF-1203 - Respuesta negativa

Una respuesta negativa debe descartar la accion pendiente y conservar la cita sin
modificaciones.

### RF-1204 - Confirmacion ambigua o vencida

La clasificacion debe basarse en una intencion afirmativa o negativa clara, no en la
coincidencia exacta con `Si` o `No`. Se permiten palabras de cortesia y variantes
afirmativas directas como `Si, por favor`, `Claro` y `Adelante`. Una respuesta
contradictoria, incierta o sin una intencion reconocible debe solicitar aclaracion.
Una confirmacion vencida debe descartarse y no ejecutar la accion.

### RF-1205 - Notificacion posterior

La notificacion al doctor y cualquier evento de cita deben producirse solamente
despues de que el proveedor confirme una cancelacion o reprogramacion exitosa.

### RF-1206 - Cita resuelta antes de confirmar

El backend no debe pedir confirmacion si la cita no se pudo recuperar. Una cita ausente
debe producir `appointment_not_found`; un fallo de lectura debe conservar su categoria
publica de agenda. Ninguno de esos casos debe crear una accion pendiente ni permitir una
mutacion al recibir un `Si` posterior.

### RF-1207 - Disponibilidad antes de confirmar una reprogramacion

Despues de resolver la cita y antes de solicitar confirmacion, el backend debe consultar
`check_availability` para el dia de destino completo y mostrar los horarios libres. Si el
paciente no indico otro dia, se usa la fecha de la cita seleccionada. Si el paciente
solicita cambiar solo la hora sin proponer una hora nueva, el backend debe mostrar primero
la lista en lugar de preguntarle una hora libre. El paciente debe elegir un horario de la
lista; una hora no ofrecida no puede crear una accion pendiente ni modificar la agenda.
La cita objetivo se resuelve usando la lista recientemente mostrada y la hora mencionada.
Si quedan varias citas candidatas, el backend pregunta cual desea cambiar antes de
consultar disponibilidad. El horario elegido queda vinculado a la misma cita y llamada
que originaron la consulta. La lista vence a los 10 minutos.

## Criterios de aceptacion

1. `Deseo cancelarla` solicita confirmacion y no cambia el estado de la cita.
2. `Si`, `Si por favor` y `Claro, adelante` despues de una solicitud de cancelacion
   ejecutan una unica cancelacion.
3. `No` y `No, gracias` conservan la cita y eliminan la accion pendiente.
4. Una solicitud de reprogramacion consulta y muestra los horarios disponibles del dia
   destino antes de pedir confirmacion.
5. La reprogramacion solo pide confirmacion despues de que el paciente elige un horario
   ofrecido; una hora no disponible no crea una accion pendiente.
6. Una confirmacion no puede reutilizarse para otra cita u operacion.
7. Una accion vencida no modifica la agenda.
8. Ninguna solicitud pendiente genera una notificacion al doctor.
9. Una operacion confirmada genera la notificacion existente una sola vez.
10. La confirmacion de cancelacion muestra fecha, horario y motivo de la cita sin
   exponer su ID interno.
11. Una respuesta contradictoria como `Si, pero mejor no` o incierta como `No estoy
    seguro` solicita aclaracion y no modifica la agenda.
12. Una cita no encontrada o una lectura fallida no genera una pregunta de confirmacion,
     no crea estado pendiente y no cambia ni notifica la agenda.
13. `Quisiera modificar esa cita y cambiar su hora` despues de listar una cita muestra
     inmediatamente los horarios disponibles de esa cita y no pregunta primero la hora
     preferida.
14. Si el listado reciente contiene varias citas, el backend identifica la mencionada; si
    no puede resolver una sola, pregunta cuál antes de mostrar horarios o cambiarla.

## Fuera del alcance

- Confirmacion de la creacion de una cita.
- Botones interactivos o plantillas especiales de WhatsApp.
- Confirmaciones por voz o por un canal diferente de WhatsApp.
