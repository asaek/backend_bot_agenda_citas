# Diseño tecnico: webhook de WhatsApp

## Estado

Etapa 2 verificada con Meta desde la Raspberry Pi. La respuesta fija fue aceptada
por WhatsApp Cloud API despues de renovar el token de acceso.

## Componentes

- Python ejecuta la logica del backend.
- FastAPI define las operaciones HTTP.
- Uvicorn sirve la aplicacion mediante ASGI.
- ngrok dirige una URL HTTPS publica hacia `localhost:8000`.
- Meta verifica la URL y envia los eventos de WhatsApp.
- `WhatsAppClient` construye y envia mensajes de texto mediante WhatsApp Cloud
  API.

## Interfaces HTTP

### `GET /`

Devuelve un objeto JSON que confirma que el proceso esta activo.

### `GET /webhook/whatsapp`

Entradas esperadas:

- `hub.mode`
- `hub.verify_token`
- `hub.challenge`

Cuando `hub.mode` es `subscribe` y el token coincide con
`WHATSAPP_VERIFY_TOKEN`, devuelve el challenge como texto plano. En caso
contrario devuelve `403 Forbidden`.

### `POST /webhook/whatsapp`

Lee el cuerpo como JSON y recorre `entry[].changes[].value.messages[]`. Para cada
mensaje con `type: "text"` extrae:

- `from` como remitente.
- `id` como ID del mensaje.
- `type` como tipo.
- `text.body` como texto.

Los mensajes sin esa estructura o con un tipo distinto de `text` se ignoran. Para
cada mensaje de texto valido llama a `WhatsAppClient.send_text` con la respuesta
fija de prueba y devuelve `200 OK`.

## Flujo de verificacion

```text
Meta -> GET /webhook/whatsapp -> validar token -> devolver challenge -> Meta
```

## Flujo de un evento

```text
WhatsApp -> Meta -> ngrok -> POST /webhook/whatsapp -> parsear texto ->
WhatsApp Cloud API -> 200 OK
```

## Configuracion

| Variable | Uso |
| --- | --- |
| `WHATSAPP_VERIFY_TOKEN` | Comparar el token enviado por Meta durante la verificacion |
| `WHATSAPP_ACCESS_TOKEN` | Autenticar el envio de mensajes mediante Cloud API |
| `WHATSAPP_PHONE_NUMBER_ID` | Identificar el numero desde el que se responde |

El cliente usa el endpoint `https://graph.facebook.com/v23.0/{PHONE_NUMBER_ID}/messages`.
Los tres valores se configuran solamente en el entorno de la Raspberry Pi y no se
guardan en el repositorio. Durante el arranque, la aplicacion carga el archivo
`.env` de la raiz si existe; las variables ya exportadas no se sobrescriben.

## Archivos de implementacion

- `main.py`: aplicacion, parseo y endpoints.
- `whatsapp_client.py`: cliente de salida para WhatsApp Cloud API.
- `pyproject.toml`: metadatos y dependencias directas.
- `uv.lock`: versiones resueltas de las dependencias.

## Manejo de errores actual

- Variable de entorno ausente: `500 Internal Server Error`.
- Verificacion invalida: `403 Forbidden`.
- Cuerpo que no sea JSON valido: respuesta de error generada por el framework.
- Error de WhatsApp Cloud API: `502 Bad Gateway`.

## Riesgos conocidos

- ngrok proporciona una URL de desarrollo temporal.
- El endpoint todavia no verifica que el evento provenga de Meta.
- La respuesta fija no es una respuesta conversacional ni debe exponerse a
  pacientes reales.
- La version de Graph API esta fijada en codigo y debera revisarse al actualizar
  la integracion.
