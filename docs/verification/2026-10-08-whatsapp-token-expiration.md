# Recuperacion del envio de WhatsApp por token vencido

## Fecha y estado

8 de octubre de 2026. Causa confirmada y envio recuperado con el token local vigente,
transferido por autorizacion explicita del usuario.

## Reproduccion

La Raspberry recibia mensajes nuevos, pero las respuestas quedaban en `failed`.
El backend y los webhooks local/publico respondian HTTP 200: esas verificaciones
no prueban que WhatsApp Cloud API acepte un envio autenticado.

La comprobacion de solo lectura exige que la respuesta del ultimo mensaje entrante
este en `sent` y tenga identificador del proveedor. Antes de corregir la credencial:

```text
LATEST_REPLY_CHECK {'incoming_id': 393, 'reply_id': 394, 'status': 'failed', 'provider_id_present': False}
FAIL: el ultimo mensaje entrante no tiene una respuesta enviada
```

Una consulta autenticada a Meta con el token de la Pi devolvio:

```text
HTTP 401
OAuthException
code: 190
error_subcode: 463
```

El subcodigo confirma expiracion del token. No habia fallos recientes del LLM
registrados para los mensajes que estaban fallando. El token del `.env` local era
distinto y paso una comprobacion con HTTP 200 contra el numero configurado en la Pi.
Las sincronizaciones generales previas excluyeron `.env` conforme al flujo del repo.

## Recuperacion

1. El usuario autorizo copiar exclusivamente `WHATSAPP_ACCESS_TOKEN` y reintentar
   la ultima respuesta fallida.
2. Se valido otra vez el candidato contra Meta antes de escribirlo. Se transfirio
   por entrada estandar de SSH, sin valores en argumentos, terminal ni documentacion.
3. La comparacion en memoria confirmo que la Pi guardo el token local, con el resto
   de las claves conservadas y modo `600`.
4. Se inspeccionaron unidades de sistema/usuario, proceso, directorio y puerto. Se
   reinicio solo el Uvicorn verificado, PID `172934` a `185562`, desde
   `/home/asaek/Downloads/chatbot_test_repo`. El nuevo proceso recibio el token fresco
   leido de `.env`; una comparacion en memoria confirmo coincidencia con ese archivo.
   Ngrok siguio activo con PID `67420`.
5. Se reenvio exclusivamente el cuerpo de la respuesta persistida para el mensaje
   entrante `393`, usando `WhatsAppClient.send_text()`. No se regenero la respuesta
   ni se repitio la solicitud de agenda. Meta devolvio identificador de envio y
   `ConversationService.record_reply_sent()` actualizo el registro existente `394`.
6. El mismo criterio operativo que fallo antes paso despues:

```text
LATEST_REPLY_CHECK {'incoming_id': 393, 'reply_id': 394, 'status': 'sent', 'provider_id_present': True}
PASS
```

## Rutas verificadas

Con `curl`, token de verificacion leido en memoria y POST de eventos vacios:

```text
local  GET /                 -> 200, {"status":"ok"}
local  GET /webhook/whatsapp  -> 200, desafio esperado
local  POST /webhook/whatsapp -> 200, {"status":"ok"}
public GET /                 -> 200, {"status":"ok"}
public GET /webhook/whatsapp  -> 200, desafio esperado
public POST /webhook/whatsapp -> 200, {"status":"ok"}
```

La evidencia confirma recepcion previa del mensaje, recuperacion del envio y
aceptacion por Meta; no registra una confirmacion de lectura del destinatario.
No se modifico codigo de la aplicacion. La regresion operativa contra la credencial
real y SQLite comprueba esta incidencia; una prueba con un token falso no reproduciria
la expiracion de la credencial del runtime.
