# Aviso de cancelacion no recibido — ventana de Meta, 22/10/2026

## Sintoma y registro existente

El usuario confirmo una cancelacion correcta desde voz y no recibio el aviso en
el WhatsApp del doctor. La accion de las 17:50:20 UTC estaba `completed`; su evento
figuraba `sent` y tenia una unica entrega aceptada por Cloud API a las 17:50:46 UTC,
con ID del proveedor y sin error sincrono.

La configuracion efectiva de texto y voz coincidía con `.env`, las credenciales
se habian validado con HTTP 200 y el contacto resuelto por Meta coincidia con el
destinatario configurado. El ultimo mensaje entrante registrado del doctor era
del 17 de octubre a las 23:18:51 UTC: aproximadamente 114,6 horas antes del diagnostico.

## Bucle de reproduccion real

Se añadio temporalmente una captura de estados al webhook de texto, se sincronizo
desde el checkout local y se recargo solo el PID verificado del puerto 8000. La
captura registro ID de correlacion, estado y codigos numericos, sin tokens ni
contenido de conversaciones. El laboratorio y ngrok continuaron activos.

Un script enviado por SSH ejecuto `WhatsAppClient.send_text()` con un unico texto
de comprobacion al doctor y correlaciono el ID devuelto con el callback. El script
exigia un estado `delivered` o `read`. Resultado real:

```text
api_accepted=true
resolved_contact_matches_doctor=true
provider_delivery_status=failed
error_codes=[131047]
AssertionError: El aviso aceptado por Meta no fue entregado al medico
```

No se repitio la operacion de agenda ni se restablecio su accion como pendiente.
El mensaje de comprobacion fue rechazado por Meta; no se uso como evidencia de
recepcion en el telefono ni se marcaron cambios artificiales en el aviso original.

## Causa confirmada y limitacion actual

El error 131047 corresponde al envio de texto libre fuera de la ventana de
24 horas desde el ultimo mensaje del destinatario al numero del bot. La direccion
del aviso sigue siendo bot -> doctor. Un mensaje del doctor al bot solo abre esa
ventana; no invierte emisor y destinatario de la notificacion.

El cliente actual usa texto libre. El envio automatico fuera de ventana necesita
una plantilla aprobada por Meta, aun no implementada/configurada en este corte.
Una llamada desde `/lab` no cuenta como mensaje de WhatsApp del doctor.

El estado local `sent` significa aceptacion inicial de Cloud API. Los callbacks
asincronos se reconocen sin persistirse actualmente; por eso la base no reflejo el
rechazo posterior. Persistir estados y codigos seguros queda pendiente en 011.

## Estado y siguiente paso

Diagnostico confirmado. La instrumentacion temporal se retira y se restituye el
webhook. La recuperacion del aviso original requiere una ventana abierta por el
doctor o una plantilla aprobada utilizable. No se declara solucionada la recepcion
mientras no exista confirmacion de entrega.
