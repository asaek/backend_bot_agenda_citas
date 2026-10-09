# Diseno - Reintentos seguros de webhook

## Estado

Implementado conforme al plan solicitado y verificado con la suite completa.
El despliegue pasa health, webhooks y autenticacion externa. El bloqueo inicial
por token vencido se resolvio con la configuracion local actualizada, como
registra la evidencia de recuperacion del 8 de octubre de 2026.

## Frontera

`reply_delivery.py` coordinara exclusiones por paciente, preparacion persistente
y auditoria de envios, mediante `ReplyDeliveryRepository`. El webhook conserva
la composicion del runtime y el tratamiento de errores publicos.

El bloqueo asincrono se obtiene antes de recibir el mensaje y se mantiene hasta
terminar su respuesta y notificaciones. Se comparte entre servicios creados por
solicitud y se libera ante excepciones o cancelacion. Las referencias debiles
evitan conservar un bloqueo por cada paciente atendido para siempre.

## Persistencia aditiva

- `reply_outbox`: una fila por mensaje entrante, con estado de procesamiento,
  cuerpo preparado y snapshot de eventos de cita. Estados: `processing`, `ready`,
  `sending`, `sent`, `failed`, `superseded`, `uncertain`.
- `reply_delivery_attempts`: una fila por intento real de salida, con fechas,
  estado, ID del proveedor y tipo/codigo seguro del error.
- `messages` conserva sus contratos y estados existentes.

Un turno es obsoleto si existe una respuesta preparada o saliente para un mensaje
posterior de la misma conversacion. Un mensaje posterior solamente recibido no
constituye prueba de que el turno anterior ya fue atendido.

Antes de generar se reclama una fila de procesamiento. Antes de enviar se guarda
la respuesta final junto con sus eventos. Los reintentos cargan esa misma respuesta.
Las respuestas `failed` anteriores a este cambio se importan sin regenerarlas.

Los estados `processing` o `sending` abandonados no autorizan otra generacion o
envio: podrian haber ocurrido efectos externos. Los errores de configuracion,
conexion antes del envio o rechazo HTTP permiten reintentar; los errores de
lectura/escritura o cancelacion durante el envio se conservan como inciertos.

## Notificaciones

El snapshot permite entregar la notificacion al doctor despues de recuperar un
envio al paciente, sin recrear ni modificar la cita. Se conserva la idempotencia
existente por `event_key` y destinatario.

## Contexto

`build_chat_messages()` filtra el historial por el mensaje entrante del turno y
por `reply_to_message_id` antes de aplicar el limite de mensajes.
