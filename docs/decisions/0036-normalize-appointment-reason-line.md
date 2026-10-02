# ADR 0036 - Normalizacion del bloque de motivo de cita

## Estado

Aceptada.

## Contexto

Aunque el prompt muestra un bloque de tres lineas, Groq puede devolver
`*Motivo de consulta:* ojos rojos` en una sola linea o insertar un renglon vacio
antes del motivo. La respuesta recibida por WhatsApp no respetaria entonces la
estructura solicitada.

## Decision

Despues de convertir tablas reconocibles, `format_whatsapp_reply()` normaliza la
etiqueta `Motivo de consulta:`. Si el modelo adjunta el motivo a la etiqueta o deja
lineas vacias intermedias, el backend mueve el motivo inmediatamente debajo de la
etiqueta y conserva su texto.

## Consecuencias

- La estructura de tres lineas no depende exclusivamente de que el LLM siga el
  prompt.
- La negrita compatible con WhatsApp y el motivo original se conservan.
- Una regresion cubre tanto texto unido a la etiqueta como lineas vacias intermedias.
