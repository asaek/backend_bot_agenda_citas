# 001 - Webhook de WhatsApp

## Estado

Etapa 2 implementada localmente. Falta verificarla con Meta y ejecutar la prueba
real desde la Raspberry Pi.

## Problema

Meta necesita una URL HTTPS publica para verificar el webhook y entregar los
eventos generados cuando un usuario envia un mensaje al numero de prueba.

## Objetivo

Recibir en el backend local un evento real de WhatsApp, procesar inicialmente sus
mensajes de texto y responder con un texto fijo de prueba mediante WhatsApp Cloud
API.

## Requisitos funcionales

### RF-001 - Estado del backend

El backend debe ofrecer una operacion que confirme que esta funcionando.

### RF-002 - Verificacion del webhook

El backend debe aceptar `GET /webhook/whatsapp`, validar el Verify Token
configurado y devolver el challenge recibido cuando la validacion sea correcta.

### RF-003 - Rechazo de una verificacion invalida

El backend debe rechazar una solicitud cuyo Verify Token no coincida con el
token configurado.

### RF-004 - Recepcion de eventos

El backend debe aceptar eventos JSON enviados por Meta a
`POST /webhook/whatsapp`.

### RF-005 - Parseo de mensajes de texto

El backend debe recorrer la estructura de Meta y extraer, para cada mensaje de
texto, el remitente (`from`), el ID (`id`), el tipo (`type`) y el cuerpo
(`text.body`).

### RF-006 - Ignorar mensajes no soportados

El backend debe ignorar temporalmente mensajes que no sean de tipo `text`, asi
como eventos de estado que no contengan mensajes.

### RF-007 - Respuesta fija de prueba

Para cada mensaje de texto valido, el backend debe enviar al remitente la
respuesta fija `Hola, recibimos tu mensaje. Esta es una respuesta de prueba.`
mediante WhatsApp Cloud API. No debe invocar un LLM ni Conversation Service.

### RF-008 - Confirmacion de recepcion

El backend debe responder exitosamente despues de recibir el evento para que
Meta no lo considere fallido.

## Criterios de aceptacion

1. Dado que el backend esta activo, al consultar su estado responde `200 OK`.
2. Dado un Verify Token correcto, la verificacion devuelve exactamente el
   challenge recibido y responde `200 OK`.
3. Dado un Verify Token incorrecto, la verificacion responde `403 Forbidden`.
4. Dado un Verify Token correcto en `GET /webhook/whatsapp`, la verificacion
   devuelve el challenge recibido y responde `200 OK`.
5. Dado un evento valido en `POST /webhook/whatsapp` con un mensaje de texto, se
   extraen sus cuatro campos y se construye una solicitud de respuesta para el
   remitente.
6. Dado un evento de estado o un mensaje no textual, el backend responde `200 OK`
   sin intentar enviar una respuesta.
7. Dado que el webhook fue registrado y suscrito unicamente al campo `messages`,
   al enviar `Hola` desde WhatsApp el usuario recibe la respuesta fija.

## Fuera de alcance

- Guardar mensajes.
- Generar respuestas con un LLM o Conversation Service.
- Verificar la firma criptografica de los eventos.
- Procesar imagenes, audio, documentos, ubicaciones o reacciones.

## Preguntas abiertas

- ¿La verificacion de firma debe formar parte de la siguiente especificacion o
  de la preparacion para produccion?
