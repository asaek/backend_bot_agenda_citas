# Pendientes y reintentos durables — 22/10/2026

El corte posterior de [callbacks de Meta](2026-10-22-meta-delivery-statuses.md)
separa aceptacion de entrega informada y alimenta esta politica con fallos
asincronos. La evidencia siguiente corresponde al estado previo de reintentos.

## Alcance implementado

Chat y laboratorio comparten `NotificationRecoveryWorker`: recuperacion al
arrancar y cada 60 segundos, cierre supervisado y exclusion de eventos ya
procesados en el ciclo. Chat importa solamente eventos persistidos de respuestas
aceptadas al paciente, incluyendo la interrupcion anterior a capturar la entrega.
Tambien se recupera la bandeja por destinatario con su propio snapshot. No se
invoca el ejecutor de herramientas ni se reconstruyen eventos desde la agenda.

La primera captura fija los destinatarios y conserva `event_json` y un contexto
acotado con nombre e historial. Una composicion diferida usa ese snapshot aunque
se actualice el perfil. El cuerpo, los datos y el payload preparado siguen
congelados. Agregar un doctor no agrega envios retroactivos; retirarlo detiene
sus entregas hasta volver a configurarlo.

## Espera y resultados

| Resultado | Comportamiento persistido |
| --- | --- |
| Conexion previa al despacho, 429/5xx o error transitorio de Meta | Espera de 60, 120, 240 s, etc., hasta 3600 s |
| `Retry-After` mas largo | Respetado hasta 24 h |
| Error de composicion | Espera persistida, sin contar un envio WhatsApp |
| Rechazo de configuracion/autenticacion | Detenido con la misma configuracion, aunque pase el tiempo |
| Respuesta perdida, sin ID o interrupcion durante el despacho | `sending` incierto, sin liberacion automatica por tiempo |
| Aceptacion conciliada | `sent` con ID recuperado, sin otro envio |
| No entrega comprobada y conciliada | Nuevo intento habilitado, conservando el contenido |

La reclamacion SQL tambien comprueba elegibilidad y espera. La huella relevante
incluye transporte, plantilla, destinatario y credenciales, sin persistirlas
literalmente ni imprimir sus valores o huellas. Corregir una configuracion
rechazada puede preparar otro payload; el intento rechazado permanece auditado.
Los reintentos transitorios reutilizan el payload original.

`doctor_notification_attempts` guarda contenido, parametros, revision local,
fechas, codigos seguros, ID del proveedor y conciliaciones. La revision local es
una huella de la configuracion de plantilla; no representa una revision de Meta
que no se haya proporcionado. Los resultados tardios comparan el numero de
intento para no sobreescribir una conciliacion ni otro intento.

## Conciliacion

`scripts/reconcile_doctor_notification.py` requiere base existente, ID del aviso,
numero de intento y referencia tecnica a evidencia externa. Admite:

- `accepted`: exige el ID recuperado de Meta y evita otro envio.
- `not_delivered`: habilita reintento tras comprobar ausencia de entrega.
- `configuration_fixed`: libera un bloqueo despues de una correccion externa
  que no haya cambiado las variables, por ejemplo aprobacion en Meta.

La utilidad no envia mensajes ni opera sobre citas. Debe verificarse que el
intento termino; una interrupcion requiere comprobar que el proceso no siga
despachando. Un timeout por si solo no prueba ausencia de entrega. Se rechazan
IDs o intentos obsoletos y las evidencias se conservan en la auditoria. Los fallos
historicos sin clasificacion quedan detenidos para revision, sin inventar intentos.

## Verificacion ejecutable

El primer bucle fallo porque la entrega no tenia `next_attempt_at`. Tras implementar
la politica, el mismo caso verifica que un fallo de conexion no se repita antes
del minuto persistido y que se recupere despues de reabrir SQLite.

Suite completa final, ejecutada despues de sincronizar fuentes y SDD desde Mac:
**533 pruebas, OK**, en 79,795 s.

```sh
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes asaek@192.168.1.12 \
  'env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo/tests:/home/asaek/Downloads/chatbot_test_repo /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -B -c '\''import os,unittest; os.chdir("/home/asaek/Downloads/chatbot_test_repo"); result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover("tests")); raise SystemExit(not result.wasSuccessful())'\'''
```

Los casos nuevos cubren:

- Fecha de reintento persistida, `Retry-After`, crecimiento exponencial y pausa de
  un rechazo 401 hasta cambiar credenciales.
- Versiones y payloads de una plantilla rechazada y corregida, sin perder el
  intento anterior ni regenerar el cuerpo.
- Respuestas inciertas, texto sin ID, conciliacion negativa/positiva y rechazo de
  un numero de intento incorrecto o una respuesta tardia.
- Destinatarios originales, incluso ante fallo de composicion.
- Recuperacion de chat tras interrumpir la captura, sin nuevo mensaje, conservando
  contexto previo a cambios de perfil y sin repetir citas o confirmaciones.
- Dos recuperadores concurrentes sin doble despacho y arranque/cierre desde el
  lifespan real de FastAPI.
- Espera y recuperacion de laboratorio, con relojes controlados y sin dormir un
  minuto en las pruebas.
- Migracion repetida de bases de chat/voz con avisos enviados, fallidos e inciertos,
  conservando sus resultados y deteniendo los fallos antiguos sin clasificacion.

Se usan dobles de WhatsApp/LLM, relojes controlados y SQLite temporal. La utilidad
de conciliacion se comprobo con `--help` en Raspberry; sus operaciones se verifican
en las pruebas del servicio, sin conciliar avisos operativos reales.

## Raspberry y configuracion

- Fuentes sincronizadas; `.env` completo copiado y comparado en memoria, modo `600`.
- Transporte `template`; nombre, idioma y componentes reales permanecen vacios.
- Sin unidad systemd del proyecto ni sesion de laboratorio activa al recargar.
- Backend: PID `131438` reemplazado por `198807`, puerto 8000.
- Laboratorio: PID `131500` reemplazado por `198874`, puerto 8001.
- Los valores administrados de ambos procesos coinciden con `.env`.
- Ngrok PID `22863` conservado.
- Ambas bases contienen columnas de recuperacion y la tabla de intentos.
- Permanecen 47 avisos historicos de chat y 1 de voz. No se inventaron intentos
  historicos: ambas auditorias operativas nuevas conservan cero filas.
- Los registros de arranque no contienen errores del ciclo de recuperacion.

| Ruta | Directa en Raspberry | Publica por ngrok |
| --- | --- | --- |
| `GET /` | 200 y cuerpo esperado | 200 y cuerpo esperado |
| `GET /webhook/whatsapp` | 200 y challenge correcto | 200 y challenge correcto |
| `POST /webhook/whatsapp`, evento vacio | 200 y cuerpo esperado | 200 y cuerpo esperado |

`GET /lab/health` devolvio 200, estado `ok`, audio `realtime`. Los checks no
crearon gestiones ni enviaron mensajes reales.

## Limites operativos

Meta sigue devolviendo HTTP `401`, codigo `190`, subcodigo `463` al consultar el
recurso del numero con `fields=id`: la credencial de envio esta vencida. Se
verifican recuperacion, persistencia, configuracion y rutas; no una nueva entrega
real ni una autenticacion saludable. La plantilla real y los callbacks durables
siguen pendientes. La aceptacion local o conciliada no demuestra entrega al telefono.
