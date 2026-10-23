# Configuracion de plantilla y captura diferida — 22/10/2026

Esta evidencia corresponde al corte de preparacion. El adaptador de envio se
implemento posteriormente y se verifica en
[envio por plantilla](2026-10-22-doctor-template-delivery.md); el contrato real
aprobado sigue pendiente.

## Alcance implementado

Se incorporan estas variables al contrato, `.env.example` y configuracion local:

```dotenv
DOCTOR_NOTIFICATION_TRANSPORT=template
DOCTOR_WHATSAPP_TEMPLATE_NAME=
DOCTOR_WHATSAPP_TEMPLATE_LANGUAGE=
```

Los destinatarios siguen resolviendose desde `DOCTOR_WHATSAPP_NUMBERS`.
`DOCTOR_NOTIFICATIONS_ENABLED` controla la captura. El transporte omitido conserva
`text` para las instalaciones existentes; el ejemplo y el runtime seleccionan
`template` explicitamente.

Con datos incompletos, `DoctorNotificationTrigger` conserva entregas `pending`
con `Configuración de plantilla incompleta.`, sin resumir, reclamar intentos ni
invocar WhatsApp. Un consumidor directo del entregador aplica la misma puerta.
Los estados `sent` y `sending` inciertos y los cuerpos preparados se conservan.
Los datos invalidos retienen el aviso con un motivo estable, sin volcar valores
de configuracion al error ni cambiar al transporte de texto automaticamente.

Las bandejas existentes conservan el evento: `reply_outbox` en chat mantiene
`notifications_completed=0`; el laboratorio mantiene `voice_notification_events`
pendiente para su ciclo existente. Los marcadores de composicion pendiente y
fallida se completan antes de cualquier envio. Este corte no cambia el esquema
ni agrega servicios o ciclos periodicos nuevos.

## Verificacion ejecutable

Antes de implementar el contrato, la prueba de configuracion incompleta fallo
por ausencia de `transport`. Antes de incorporar la retencion, la prueba del
webhook fallo porque intentaba enviar un cuarto mensaje al doctor por texto.
Ambas pasaron despues de implementar sus respectivos cambios.

Se ejecutaron las pruebas despues de sincronizar cada cambio local con Raspberry:

- Seleccion de webhook, entregador y laboratorio: **74 pruebas, OK**, en 7,945 s.
- Suite completa: **506 pruebas, OK**, en 73,264 s.

Comando de la suite completa:

```sh
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes asaek@192.168.1.12 \
  'env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo/tests:/home/asaek/Downloads/chatbot_test_repo /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -B -c '\''import os,unittest; os.chdir("/home/asaek/Downloads/chatbot_test_repo"); result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover("tests")); raise SystemExit(not result.wasSuccessful())'\'''
```

Los casos nuevos comprueban nombre o idioma vacios, datos mal formados,
transporte desconocido, varios doctores, cero intentos durante la retencion,
preservacion de estados enviados/inciertos y ausencia de respaldo por texto.
La prueba del webhook confirma al paciente una sola vez y conserva el evento
tras duplicados y reapertura; al seleccionar explicitamente el transporte de
texto existente recupera el aviso sin repetir la cita. El laboratorio repite
esa comprobacion tras cerrar y reabrir su repositorio, incluso con el resumidor
no disponible mientras la plantilla esta incompleta. Todo ello usa dobles y
SQLite temporal, sin enviar mensajes reales.

## Configuracion y runtime de Raspberry

- `.env` fue copiado completo por SSH; igualdad byte por byte confirmada en memoria
  y permisos remotos `600`, sin imprimir valores ni hashes.
- Se verificaron los listeners, comandos y directorios de ambos procesos; no habia
  unidad systemd del proyecto ni llamada/mensaje de laboratorio activo.
- Backend: PID `3965734` reemplazado por `107947`, puerto 8000.
- Laboratorio: PID `3939340` reemplazado por `108009`, puerto 8001.
- Los valores administrados de ambos procesos coinciden con `.env`; transporte
  `template`, nombre vacio e idioma vacio.
- El proceso ngrok existente se conservo.

| Ruta | Directa en Raspberry | Publica por ngrok |
| --- | --- | --- |
| `GET /` | 200, cuerpo esperado | 200, cuerpo esperado |
| `GET /webhook/whatsapp` | 200, challenge correcto | 200, challenge correcto |
| `POST /webhook/whatsapp`, evento vacio | 200, cuerpo esperado | 200, cuerpo esperado |

`GET /lab/health` devolvio 200, estado `ok`, audio `realtime`. Los checks de webhook
usaron el token de verificacion en memoria y no generaron gestiones ni avisos.

## Limites y siguiente corte

Nombre e idioma se validan solo por formato, sin comprobar aprobacion de Meta ni
asumir componentes. Con datos completos validos el aviso permanece retenido con
`Envío por plantilla pendiente de implementación.`. `send_template()`, mapeo
aprobado, recuperacion periodica de chat y callbacks persistentes son trabajo
posterior.

La consulta autenticada de solo lectura a Meta devolvio HTTP `401`, codigo `190`,
subcodigo `463`: el token de envio sigue vencido. Las rutas y la configuracion
estan comprobadas, pero no se acredita un nuevo envio real ni una autenticacion
Meta saludable. El corte de retencion funciona sin depender de esa credencial.
