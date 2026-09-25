# Tareas - Notificaciones al doctor

## Corte 0 - SDD y contrato funcional

- [x] Confirmar que las tres operaciones de cita son los unicos disparadores.
- [x] Definir el resumen como contenido obligatorio de cada notificacion.
- [x] Registrar criterios de aceptacion, privacidad y limites de alcance.
- [x] Dejar el diseno tecnico en estado borrador hasta implementarlo.

## Corte 1 - Eventos de agenda

- [x] Definir los tipos de evento de notificacion.
- [x] Exponer los resultados exitosos de create, reschedule y cancel al flujo de
  notificacion.
- [x] Relacionar cada evento con el mensaje entrante y la llamada de herramienta.
- [x] Probar que los errores de agenda no generan eventos exitosos.

## Corte 2 - Persistencia e idempotencia

- [x] Crear la tabla `doctor_notifications` y sus restricciones.
- [x] Implementar el repositorio de estados, errores e IDs del proveedor.
- [x] Implementar la clave unica `(event_key, recipient_number)` para evitar
  duplicados por destinatario.
- [x] Probar reintentos de encolado y recuperacion de estados pendientes o fallidos.
- [x] Probar entregas independientes para varios numeros configurados.

## Corte 3 - Composicion del mensaje y resumen

- [x] Implementar el formato unico para agendamiento, modificacion y cancelacion.
- [x] Implementar el resumen con el historial persistido y el contexto de la cita.
- [x] Incluir paciente, sus ultimos 10 digitos de telefono y senales de prioridad
  disponibles.
- [x] Evitar diagnosticos, transcripciones completas e identificadores internos.
- [x] Probar la composicion con un proveedor LLM falso y con nombre de paciente
  ausente.

## Corte 4 - Entrega por WhatsApp

- [x] Agregar la configuracion de varios doctores y la bandera de habilitacion.
- [x] Reutilizar `WhatsAppClient` para cada destinatario configurado.
- [x] Persistir correctamente estados `pending`, `sending`, `sent` y `failed` por
  destinatario.
- [x] Normalizar errores de configuracion y de la API externa.
- [x] Probar envios multiples, fallo aislado y reintento con un cliente WhatsApp
  falso.

## Corte 5 - Integracion del webhook

- [x] Componer `DoctorNotificationService` desde `main.py`.
- [x] Integrar la notificacion despues de cada operacion de cita confirmada.
- [x] Garantizar que un fallo al doctor no impida la respuesta al paciente.
- [x] Probar los tres eventos desde el ciclo completo del webhook.
- [x] Probar que un webhook duplicado no envia dos mensajes al mismo doctor.

## Corte 6 - Verificacion y cierre documental

- [x] Actualizar README y `.env.example` con la configuracion implementada.
- [x] Cambiar la especificacion y el ADR a estado implementado cuando corresponda.
- [x] Ejecutar la suite completa en la Raspberry Pi.
- [x] Verificar health check y ambos metodos del webhook con los comandos del
  README.
- [x] Registrar la evidencia en `docs/verification/`.

La evidencia de cierre esta en
`docs/verification/2026-09-22-doctor-notifications-webhook.md` e incluye la suite
local, la suite del mirror de Raspberry Pi y la verificacion HTTP operativa.

## Fuera de este corte

- [ ] Agregar un worker o una cola distribuida para notificaciones.
- [ ] Agregar canales diferentes de WhatsApp.
- [ ] Generar resumenes por inactividad o cierre automatico de la conversacion.
