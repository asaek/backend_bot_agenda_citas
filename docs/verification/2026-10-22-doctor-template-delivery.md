# Envio mediante plantilla de Meta — 22/10/2026

Esta evidencia corresponde al adaptador de plantilla. El corte posterior de
[recuperacion y reintentos](2026-10-22-doctor-notification-retries.md) incorpora
el procesamiento periodico de chat, espera persistida y conciliacion explicita.

## Implementacion

`WhatsAppClient.send_template()` envia al mismo endpoint de Cloud API v23.0 el
destinatario, `type=template`, nombre, codigo de idioma y componentes explicitos.
Texto y plantilla comparten autenticacion, timeout y propagacion de errores HTTP.

El compositor expone los mismos datos saneados del aviso actual: evento, estado,
fecha, hora, motivo, nombre/telefono, resumen y señales de prioridad. La entrada
comun de chat y laboratorio los conserva junto al cuerpo. El mapeo JSON de
`DOCTOR_WHATSAPP_TEMPLATE_COMPONENTS` permite agrupar datos y preserva el orden y
los nombres de parametros aprobados; no fija la cantidad ni el layout real.
Admite parametros de texto en encabezado, cuerpo y botones URL.

Los campos desconocidos, expresiones, mapeos que pierdan datos o datos ausentes
retienen el aviso antes del despacho. Los parametros compactan saltos y
tabuladores sin recortar los datos. El modo plantilla no cae a texto libre.
`notification_body` es una referencia explicita al cuerpo completo, util tambien
para registros historicos sin datos estructurados; no se extraen campos por
heuristicas ni se inventan valores faltantes.

`template_data_json` conserva los datos junto al cuerpo y `template_payload_json`
congela nombre, idioma y componentes al reclamar un envio. Los reintentos conocidos
reutilizan ese payload, incluso tras reiniciar o cambiar la configuracion. Las
migraciones idempotentes de chat y voz agregan columnas opcionales preservando
avisos historicos. Una respuesta perdida o sin ID de Meta queda incierta sin
reenvio automatico; `sent` sigue significando aceptacion inicial, no entrega.

## Pruebas

Los primeros bucles reprodujeron ausencia de `send_template`, ausencia del contrato
de datos del entregador, cero plantillas desde el webhook y el marcado indebido
como `sent` de una respuesta sin ID. Cada prueba paso tras su cambio correspondiente.

Seleccion de cliente, webhook, composicion, entregador, mapeo, persistencia y voz:
**111 pruebas, OK**, antes de añadir los casos finales de rechazo HTTP y respuesta
sin identificador. Suite completa final: **519 pruebas, OK**, en 73,967 s.

```sh
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes asaek@192.168.1.12 \
  'env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo/tests:/home/asaek/Downloads/chatbot_test_repo /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -B -c '\''import os,unittest; os.chdir("/home/asaek/Downloads/chatbot_test_repo"); result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover("tests")); raise SystemExit(not result.wasSuccessful())'\'''
```

La verificacion cubre:

- JSON HTTP de plantilla, autenticacion y orden de encabezado/cuerpo/boton.
- Propagacion de rechazos HTTP 400, 401 y 429.
- Agendar, reprogramar y cancelar con plantilla solo al doctor y confirmacion al
  paciente, conservando todos los datos y sin duplicados del webhook.
- Mapeos ficticios con distintas agrupaciones y parametros con o sin nombre.
- Reintento tras fallo conocido y reapertura, conservando el payload original aun
  con otra configuracion o sin resumidor disponible.
- Respuesta perdida/sin ID, retencion por datos ausentes y ausencia de respaldo
  automatico por texto.
- Migracion repetida de bases antiguas de chat y voz sin reescribir avisos enviados.

Las pruebas usan dobles HTTP/WhatsApp/LLM y SQLite temporal. Ningun layout de
prueba se configura como la plantilla operativa ni acredita aprobacion por Meta.

## Raspberry y configuracion

- Fuentes y documentacion sincronizadas desde el checkout local antes de ejecutar.
- `.env` completo copiado por SSH, igualdad en memoria y modo `600` confirmados.
- Transporte `template`; nombre, idioma y componentes reales vacios.
- Sin unidad systemd del proyecto y sin llamada/mensaje de laboratorio activo al recargar.
- Backend: PID `107947` reemplazado por `131438`, puerto 8000.
- Laboratorio: PID `108009` reemplazado por `131500`, puerto 8001.
- Los valores administrados de ambos procesos coinciden con `.env`.
- Ngrok PID `22863` conservado.
- Ambas bases operativas contienen las dos columnas nuevas; se conservan 47 avisos
  de chat y 1 de voz. La comprobacion final de esas bases fue de solo lectura.

| Comprobacion | Directa en Raspberry | Publica por ngrok |
| --- | --- | --- |
| `GET /` | 200 y cuerpo esperado | 200 y cuerpo esperado |
| `GET /webhook/whatsapp` | 200 y challenge correcto | 200 y challenge correcto |
| `POST /webhook/whatsapp`, evento vacio | 200 y cuerpo esperado | 200 y cuerpo esperado |

`GET /lab/health` devuelve 200, estado `ok`, audio `realtime`. Los checks no
generaron citas ni enviaron mensajes de WhatsApp.

## Pendiente para la prueba real

Meta devolvio HTTP `401`, codigo `190`, subcodigo `463` al consultar el recurso
del numero con `fields=id`: la credencial de envio sigue vencida. Se verifican
codigo, persistencia, configuracion y rutas, pero no una autenticacion saludable
ni una nueva entrega real.

Para activar el envio se requiere la plantilla real aprobada con su nombre,
idioma, componentes, parametros y orden exactos, ademas de credenciales vigentes.
Los callbacks persistentes y el procesamiento periodico de pendientes de chat
permanecen en los siguientes cortes. Los avisos con configuracion incompleta
siguen conservandose mientras se reciben esos datos.
