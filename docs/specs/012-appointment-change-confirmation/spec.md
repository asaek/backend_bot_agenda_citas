# 012 - Confirmacion de cambios destructivos de citas

## Estado

Implementado. La cancelacion y la reprogramacion requieren una confirmacion
explicita antes de modificar la fuente de verdad de agenda.

## Objetivo

Evitar que una solicitud ambigua, un error del LLM o una interpretacion incorrecta
cancele o modifique una cita sin que el paciente confirme la operacion exacta.

## Alcance

La funcionalidad cubre:

- Confirmacion previa para cancelar una cita.
- Confirmacion previa para reprogramar una cita a un horario concreto.
- Respuesta negativa sin cambios en la agenda.
- Expiracion de una confirmacion pendiente despues de 10 minutos.
- Emision de notificaciones al doctor solamente despues de la operacion confirmada.

La creacion de una cita no requiere esta confirmacion dentro de este alcance.

## Requisitos funcionales

### RF-1201 - Confirmacion previa

Una solicitud de `cancel_appointment` o `reschedule_appointment` no debe ejecutar
la mutacion del proveedor de calendario hasta recibir una confirmacion afirmativa
del paciente. Puede realizar una lectura de la cita para mostrar sus datos antes de
formular la pregunta.

### RF-1202 - Operacion exacta

La confirmacion debe estar vinculada a una sola operacion, cita y horario nuevo
cuando corresponda. Una confirmacion no puede autorizar otra mutacion distinta.

La pregunta de confirmacion debe mostrar los datos de la cita que se modificara:
fecha, horario y motivo. No debe mostrar el ID interno de la cita.

### RF-1203 - Respuesta negativa

Una respuesta negativa debe descartar la accion pendiente y conservar la cita sin
modificaciones.

### RF-1204 - Confirmacion ambigua o vencida

Una respuesta que no sea claramente afirmativa o negativa debe solicitar nuevamente
`Si` o `No`. Una confirmacion vencida debe descartarse y no ejecutar la accion.

### RF-1205 - Notificacion posterior

La notificacion al doctor y cualquier evento de cita deben producirse solamente
despues de que el proveedor confirme una cancelacion o reprogramacion exitosa.

## Criterios de aceptacion

1. `Deseo cancelarla` solicita confirmacion y no cambia el estado de la cita.
2. `Si` despues de una solicitud de cancelacion ejecuta una unica cancelacion.
3. `No` conserva la cita y elimina la accion pendiente.
4. Una solicitud de reprogramacion muestra el nuevo horario y requiere confirmacion.
5. Una confirmacion no puede reutilizarse para otra cita u operacion.
6. Una accion vencida no modifica la agenda.
7. Ninguna solicitud pendiente genera una notificacion al doctor.
8. Una operacion confirmada genera la notificacion existente una sola vez.
9. La confirmacion de cancelacion muestra fecha, horario y motivo de la cita sin
   exponer su ID interno.

## Fuera del alcance

- Confirmacion de la creacion de una cita.
- Botones interactivos o plantillas especiales de WhatsApp.
- Confirmaciones por voz o por un canal diferente de WhatsApp.
