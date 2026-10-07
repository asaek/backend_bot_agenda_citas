# Diagnostico de falta de respuesta por token de WhatsApp vencido

## Fecha y estado

7 de octubre de 2026. Causa confirmada y recuperacion verificada con un token renovado.

## Reproduccion

El backend y el tunel publico respondieron `HTTP 200 {"status":"ok"}`. Los mensajes
entrantes se estaban persistiendo, pero sus respuestas quedaban en `failed`.
La comprobacion de solo lectura de SQLite fallo al exigir que la ultima respuesta
estuviera en `sent`; esto reproduce la falta de respuesta reportada.

Se consulto la API de Meta con la credencial configurada, sin imprimir valores,
cabeceras, numeros de telefono ni contenido de mensajes. El resultado fue:

```text
HTTP 401
OAuthException
code: 190
error_subcode: 463
```

Meta rechazo el token del runtime por expiracion. La recepcion del webhook y el
health check seguian funcionando; esas rutas por si solas no verifican el envio
autenticado mediante WhatsApp Cloud API.

## Token local y bloqueo inicial de recuperacion

El token local era distinto del de la Pi y respondio inicialmente HTTP 200 durante
la comprobacion aislada. Al continuar la recuperacion, la validacion previa a
escribirlo volvio a consultar Meta y obtuvo HTTP 401 con `190/463`. La transferencia
se detuvo antes de modificar la configuracion.

La comprobacion a las `2026-10-07T20:26:30Z` confirmo que ese token local habia vencido
el 7 de octubre a las `13:00 PDT` (`20:00 UTC`). El archivo `.env` de la Pi tenia
modo `600`. No se guardaron credenciales ni huellas de sus valores en la evidencia.

## Recuperacion verificada

Despues de renovar el token local se ejecuto el flujo `local to raspberry`:

1. Se reviso la sincronizacion y se confirmo que los archivos del proyecto coincidieran.
2. El token local nuevo respondio HTTP 200 contra Meta. Se transfirio solamente
   `WHATSAPP_ACCESS_TOKEN` por entrada estandar de SSH; la comparacion en memoria
   confirmo coincidencia, conservacion de las demas claves y modo `600`.
3. Se verificaron proceso, puerto, directorio y unidades de sistema y usuario. Se
   reinicio solamente el proceso Uvicorn confirmado, de PID `2434069` a `2538507`,
   desde `/home/asaek/Downloads/chatbot_test_repo`.
4. Se comprobo en memoria que el nuevo proceso cargara el mismo token que el `.env`
   de la Pi, sin imprimirlo.
5. El health check local y los webhooks GET y POST local y publico respondieron
   HTTP 200 con los cuerpos esperados. El tunel ngrok existente tenia PID `19472`.
6. Se reintento la respuesta ya generada para el ultimo mensaje entrante fallido,
   sin reconstruir la solicitud de agenda. WhatsApp Cloud API acepto el envio y
   devolvio un identificador; `ConversationService.record_reply_sent()` registro
   el resultado como `sent`.

La comprobacion final a las `2026-10-07T20:37:45Z` confirmo que el mensaje entrante
interno `358` tuviera respuesta `sent` e identificador del proveedor. El mismo criterio
que habia fallado en la reproduccion ahora paso. Esta evidencia confirma aceptacion
del envio por Meta, no una confirmacion de lectura en el dispositivo del destinatario.
