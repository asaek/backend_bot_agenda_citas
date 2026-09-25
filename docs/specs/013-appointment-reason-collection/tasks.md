# Tareas - Motivo antes de crear una cita

## Corte 1 - Estado pendiente

- [x] Definir el estado pendiente de una solicitud de creacion.
- [x] Persistir el horario y la expiracion en el contexto de la conversacion.
- [x] Descartar el motivo propuesto por el LLM hasta recibir el mensaje del paciente.

## Corte 2 - Ejecucion segura

- [x] Interceptar `create_appointment` antes del proveedor.
- [x] Ejecutar la cita con el texto del siguiente mensaje del paciente.
- [x] Emitir eventos y notificaciones solo despues de una creacion exitosa.

## Corte 3 - Verificacion

- [x] Probar que la primera solicitud pregunta el motivo y no crea una cita.
- [x] Probar que el motivo recibido se persiste en la cita.
- [x] Probar continuidad despues de reiniciar `ConversationService`.
- [x] Ejecutar la suite completa en el mirror de Raspberry Pi.
- [x] Verificar health check y ambos metodos del webhook en el mirror.
