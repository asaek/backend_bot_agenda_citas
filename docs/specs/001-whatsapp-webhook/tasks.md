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
- [ ] Verificar localmente despues de sincronizar la Raspberry Pi.

## Conexion con Meta

- [ ] Elegir el Verify Token de desarrollo.
- [ ] Instalar o confirmar la disponibilidad de ngrok.
- [ ] Iniciar Uvicorn en `localhost:8000` en la Raspberry Pi.
- [ ] Crear el tunel HTTPS hacia el puerto 8000.
- [ ] Registrar `https://unthread-foam-outlast.ngrok-free.dev/webhook/whatsapp` en Meta.
- [ ] Introducir el mismo Verify Token en Meta.
- [ ] Completar la verificacion del webhook.
- [ ] Mantener suscrito unicamente el campo `messages`.

## Verificacion real

- [ ] Enviar `Hola` desde el numero personal al numero de prueba.
- [ ] Confirmar que el backend parsea el mensaje de texto.
- [ ] Confirmar que WhatsApp recibe la respuesta fija.
- [ ] Guardar un ejemplo anonimizado de la estructura para la siguiente
  especificacion.
- [ ] Revisar todos los criterios de aceptacion.
- [ ] Cambiar el estado de la especificacion a `Verificado`.
