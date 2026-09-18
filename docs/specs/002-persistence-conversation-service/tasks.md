# Tareas: persistencia y Conversation Service

## Estado

En implementacion local.

## SDD

- [x] Definir el alcance y los criterios de aceptacion.
- [x] Definir SQLite, repositorios, estado e idempotencia.
- [x] Registrar la decision tecnologica de esta etapa.

## Implementacion

- [x] Crear el esquema SQLite y la configuracion `DATABASE_PATH`.
- [x] Implementar conexiones y transacciones.
- [x] Implementar repositorios de pacientes.
- [x] Implementar repositorios de conversaciones.
- [x] Implementar repositorios de mensajes.
- [x] Implementar `ConversationService` con la respuesta fija.
- [x] Integrar el servicio con `POST /webhook/whatsapp`.
- [x] Guardar respuestas `sent` y `failed`.
- [x] Añadir deduplicacion por `provider_message_id`.

## Pruebas

- [x] Verificar que el primer mensaje crea paciente y conversacion.
- [x] Verificar que dos mensajes reutilizan paciente y conversacion.
- [x] Verificar que dos numeros generan datos independientes.
- [x] Verificar que un webhook repetido no duplica la respuesta.
- [x] Verificar que un fallo permite reintentar.
- [x] Verificar la persistencia despues de crear un nuevo servicio.
- [x] Verificar que estados y mensajes no textuales no crean datos.
- [x] Ejecutar toda la suite local.

## Raspberry Pi

- [x] Sincronizar los archivos al mirror de ejecucion.
- [x] Confirmar que `DATABASE_PATH` usa la ruta persistente predeterminada.
- [x] Ejecutar las pruebas en la Raspberry Pi.
- [x] Probar el flujo real con una cuenta de WhatsApp de prueba.
