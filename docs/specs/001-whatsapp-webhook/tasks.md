# Tareas: webhook de WhatsApp

## Estado

Etapa 2 implementada localmente; pendiente de sincronizacion, configuracion
segura en la Raspberry Pi y prueba con Meta.

Este es el unico corte de implementacion activo. La respuesta implementada es
fija y no usa LLM ni Conversation Service.

## Backend local

- [x] Inicializar el proyecto con `uv`.
- [x] Agregar FastAPI y Uvicorn.
- [x] Crear la aplicacion FastAPI.
- [x] Crear `GET /`.
- [x] Crear `GET /webhook/whatsapp`.
- [x] Leer `WHATSAPP_VERIFY_TOKEN` desde el entorno.
- [x] Crear `POST /webhook/whatsapp`.
- [x] Extraer remitente, ID, tipo y texto de mensajes de texto.
- [x] Ignorar mensajes no textuales y eventos sin mensajes.
- [x] Crear `WhatsAppClient` con `WHATSAPP_ACCESS_TOKEN` y
  `WHATSAPP_PHONE_NUMBER_ID`.
- [x] Construir la solicitud de respuesta fija mediante Cloud API.
- [x] Verificar localmente despues de sincronizar la Raspberry Pi.

## Conexion con Meta

- [x] Elegir el Verify Token de desarrollo.
- [x] Instalar o confirmar la disponibilidad de ngrok.
- [x] Iniciar Uvicorn en `localhost:8000` en la Raspberry Pi.
- [x] Crear el tunel HTTPS hacia el puerto 8000.
- [x] Registrar `https://unthread-foam-outlast.ngrok-free.dev/webhook/whatsapp` en Meta.
- [x] Introducir el mismo Verify Token en Meta.
- [x] Completar la verificacion del webhook.
- [x] Mantener suscrito unicamente el campo `messages`.

## Verificacion real

- [x] Enviar mensajes desde el numero personal al numero de prueba.
- [x] Confirmar que el backend parsea los mensajes de texto.
- [x] Confirmar que WhatsApp Cloud API acepta la respuesta fija.
- [x] Guardar un ejemplo anonimizado de la estructura para la siguiente
  especificacion.
- [x] Revisar todos los criterios de aceptacion.
- [x] Cambiar el estado de la especificacion a `Verificado`.
