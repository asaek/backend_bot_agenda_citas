# Verificacion del formato WhatsApp con negrita

## Fecha

1 de octubre de 2026.

## Formato enviado

WhatsApp reconoce negrita con asteriscos simples, no Markdown completo. El bloque
de cita conserva la lista de varias lineas y resalta sus etiquetas:

```text
- *Horario:* 10:00 a 10:30
  *Motivo de consulta:*
  revision de prueba A
```

## Normalizacion

Groq respondio HTTP 200 con dos citas ficticias. Su respuesta mantuvo las etiquetas
en negrita, pero adjunto el motivo a la etiqueta o dejo un renglon vacio. Antes de
enviar, `format_whatsapp_reply()` normaliza ambas variantes y produce el bloque
anterior sin cambiar el texto del motivo.

El caso de regresion reprodujo ambos formatos del proveedor y fallo antes de la
normalizacion porque el motivo no quedaba en su propia linea.

## Verificacion automatizada en Raspberry Pi

- [x] `test_conversation_service.py`: 31 pruebas pasan.
- [x] Suite completa: 206 pruebas pasan.
- [x] Una comprobacion directa con espacios de salto de linea produjo exactamente
  los bloques esperados.

## Runtime

Despues de sincronizar los cambios, se inspecciono el listener y se recargo
unicamente el PID Uvicorn verificado desde el directorio del proyecto. El tunel
ngrok existente siguio activo. Se verificaron las rutas localmente y por la URL
publica; el POST uso un evento de estado sin mensajes y no envio respuestas por
WhatsApp.

```text
GET /                         -> OK local y publico
GET /webhook/whatsapp         -> OK local y publico
POST /webhook/whatsapp        -> OK local y publico
```
