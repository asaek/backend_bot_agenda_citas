# Verificacion del formato de citas en WhatsApp

## Fecha

1 de octubre de 2026.

## Formato

Cada cita se presenta como un bloque independiente:

```text
- Horario: HH:MM a HH:MM
  Motivo de consulta:
  <motivo de la cita>
```

El texto del motivo se conserva. Si el listado abarca varios dias, tambien incluye
la fecha correspondiente a cada cita.

## Verificacion automatizada en Raspberry Pi

- [x] El prompt contiene el formato de tres lineas solicitado.
- [x] `test_conversation_service.py`: 30 pruebas, todas pasaron.
- [x] Suite completa: 205 pruebas, todas pasaron.

## Verificacion con Groq

Se envio al modelo una conversacion sintetica con dos citas ficticias, sin enviar
mensajes por WhatsApp ni usar datos de citas reales. Groq respondio HTTP 200 con:

```text
- Horario: 10:00 a 10:30
  Motivo de consulta:
  revision de prueba A

- Horario: 14:00 a 14:30
  Motivo de consulta:
  consulta de prueba B
```

## Runtime

Despues de sincronizar el prompt y la documentacion, se inspecciono el listener y
se recargo unicamente el PID Uvicorn verificado desde el directorio del proyecto.
El tunel ngrok existente siguio activo. Las rutas se comprobaron localmente y por
la URL publica; el POST uso un evento de estado sin mensajes y no envio respuestas
por WhatsApp.

```text
GET /                         -> OK local y publico
GET /webhook/whatsapp         -> OK local y publico
POST /webhook/whatsapp        -> OK local y publico
```
