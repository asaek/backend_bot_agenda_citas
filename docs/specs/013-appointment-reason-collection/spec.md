# 013 - Motivo antes de crear una cita

## Estado

Verificado. El backend solicita el motivo antes de crear una cita y conserva la
solicitud pendiente entre mensajes. La evidencia esta en
`docs/verification/2026-09-24-appointment-reason.md`.

## Objetivo

Evitar que una cita se cree con un motivo inventado, predeterminado o completado por
el LLM cuando el paciente de prueba todavia no ha explicado la razon de su visita.

## Alcance

La funcionalidad cubre:

- Solicitud del motivo antes de ejecutar `create_appointment`.
- Conservacion del horario solicitado mientras se espera el siguiente mensaje.
- Uso del texto del paciente como motivo de la cita.
- Persistencia del estado pendiente en `conversations.context_json`.
- Expiracion de la solicitud pendiente despues de 10 minutos.
- Eventos y notificaciones solamente despues de crear la cita correctamente.

La creacion no requiere una confirmacion adicional de Si o No despues de recibir el
motivo.

## Requisitos funcionales

### RF-1301 - Motivo previo

Una solicitud de `create_appointment` no debe modificar el proveedor de calendario
hasta que el paciente de prueba haya enviado un motivo en un mensaje posterior.
El valor `reason` propuesto por el LLM no cuenta como motivo proporcionado por el
paciente.

### RF-1302 - Horario pendiente

La pregunta por el motivo debe conservar el horario solicitado y usarlo al ejecutar
la cita posteriormente. El paciente no debe tener que repetirlo.

### RF-1303 - Texto del paciente

El motivo persistido debe derivarse del mensaje del paciente que responde la pregunta.
El backend puede normalizar espacios, pero no debe sustituirlo por una categoria o
texto predeterminado.

### RF-1304 - Persistencia

Si el proceso se reinicia despues de preguntar el motivo, el siguiente mensaje debe
continuar la misma solicitud pendiente.

### RF-1305 - Expiracion

Una solicitud pendiente con mas de 10 minutos debe descartarse sin crear una cita y
debe pedir al paciente que solicite nuevamente el horario.

### RF-1306 - Notificacion posterior

La primera pregunta no debe producir un evento de cita ni una notificacion al doctor.
Una notificacion solo puede emitirse despues de una creacion exitosa.

## Criterios de aceptacion

1. `Agendame otra cita a las 15:00` responde preguntando el motivo y no crea una
   cita.
2. `Revision de cornea` despues de la pregunta crea la cita a las 15:00 con ese
   motivo.
3. El flujo continua despues de reconstruir `ConversationService`.
4. El motivo sugerido por el LLM no se persiste si el paciente todavia no lo ha
   enviado.
5. Una solicitud fallida o vencida no produce una notificacion de exito.
6. La respuesta final no muestra IDs internos de la agenda.

## Fuera del alcance

- Clasificacion clinica o diagnostico del motivo.
- Validacion medica del texto del paciente.
- Confirmacion interactiva adicional para crear la cita.
- Botones o plantillas especiales de WhatsApp.
