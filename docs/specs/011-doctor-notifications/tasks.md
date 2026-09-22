# Tareas - Notificaciones al doctor

## Corte 0 - SDD y contrato funcional

- [x] Confirmar que las tres operaciones de cita son los unicos disparadores.
- [x] Definir el resumen como contenido obligatorio de cada notificacion.
- [x] Registrar criterios de aceptacion, privacidad y limites de alcance.
- [x] Dejar el diseno tecnico en estado borrador hasta implementarlo.

## Corte 1 - Eventos de agenda

- [ ] Definir los tipos de evento de notificacion.
- [ ] Exponer los resultados exitosos de create, reschedule y cancel al flujo de
  notificacion.
- [ ] Relacionar cada evento con el mensaje entrante y la llamada de herramienta.
- [ ] Probar que los errores de agenda no generan eventos exitosos.

## Corte 2 - Persistencia e idempotencia

- [ ] Crear la tabla `doctor_notifications` y sus restricciones.
- [ ] Implementar el repositorio de estados, errores e IDs del proveedor.
- [ ] Implementar la clave unica del evento para evitar duplicados.
- [ ] Probar reintentos del webhook y recuperacion de estados pendientes o fallidos.

## Corte 3 - Composicion del mensaje y resumen

- [ ] Implementar el formato unico para agendamiento, modificacion y cancelacion.
- [ ] Implementar el resumen con el historial persistido y el contexto de la cita.
- [ ] Incluir paciente, telefono y senales de prioridad disponibles.
- [ ] Evitar diagnosticos, transcripciones completas e identificadores internos.
- [ ] Probar la composicion con un proveedor LLM falso y con nombre de paciente
  ausente.

## Corte 4 - Entrega por WhatsApp

- [ ] Agregar la configuracion del doctor y la bandera de habilitacion.
- [ ] Reutilizar `WhatsAppClient` para el destinatario del doctor.
- [ ] Persistir correctamente estados `pending`, `sending`, `sent` y `failed`.
- [ ] Normalizar errores de configuracion y de la API externa.
- [ ] Probar envio exitoso, fallo y reintento con un cliente WhatsApp falso.

## Corte 5 - Integracion del webhook

- [ ] Componer `DoctorNotificationService` desde `main.py`.
- [ ] Integrar la notificacion despues de cada operacion de cita confirmada.
- [ ] Garantizar que un fallo al doctor no impida la respuesta al paciente.
- [ ] Probar los tres eventos desde el ciclo completo del webhook.
- [ ] Probar que un webhook duplicado no envia dos mensajes al doctor.

## Corte 6 - Verificacion y cierre documental

- [ ] Actualizar README y `.env.example` con la configuracion implementada.
- [ ] Cambiar la especificacion y el ADR a estado implementado cuando corresponda.
- [ ] Ejecutar la suite completa en la Raspberry Pi.
- [ ] Verificar health check y ambos metodos del webhook con los comandos del
  README.
- [ ] Registrar la evidencia en `docs/verification/`.

## Fuera de este corte

- [ ] Agregar un worker o una cola distribuida para notificaciones.
- [ ] Agregar canales diferentes de WhatsApp.
- [ ] Generar resumenes por inactividad o cierre automatico de la conversacion.
