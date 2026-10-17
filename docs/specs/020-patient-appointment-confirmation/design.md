# Diseno - Confirmacion de cita para el paciente

## Estado

Implementado. Decision: ADR 0053.

## Modulo compartido

`appointment_messages.py` expone `render_appointment_message(appointment, tool_name,
patient_name, audience)`. Su interfaz recibe una cita y la operacion definitiva;
el renderizado es determinista y no consulta persistencia, IA ni WhatsApp.
`AppointmentMessageAudience` distingue paciente y doctor. El modulo comparte
etiquetas de evento/estado, estructura de cita y paciente y formato del telefono.

El paciente recibe fecha `DD/MM/YYYY` y solo el inicio `h:mm AM/PM`. El doctor
recibe su fecha ISO e intervalo `HH:MM-HH:MM`. La normalizacion de espacios no
recorta el nombre ni el motivo del paciente.

## Integracion

`ConversationService._appointment_result_reply()` valida el output tipado de la
operacion exitosa, convierte sus timestamps a la zona de agenda y carga el nombre
persistido. Se usa despues de crear, cancelar y reprogramar. Los fallos y preguntas
previas conservan sus rutas actuales; no dependen del resumidor del doctor.

`render_doctor_notification()` mantiene el saneamiento de nombres/motivos y de los
datos internos antes de delegar los dos bloques al modulo compartido. Agrega
despues resumen y prioridad validados, como antes.

`_history_for_event()` reconoce el encabezado nuevo y los cierres historicos como
limite de gestiones anteriores. Se mantiene la exclusión de mensajes posteriores
y de evidencia proveniente del asistente.

La confirmacion se genera dentro de `build_reply()`, antes de `ReplyDeliveryService.prepare()`.
No se cambia el orden de entrega paciente -> doctor ni la respuesta persistida para reintentos.
