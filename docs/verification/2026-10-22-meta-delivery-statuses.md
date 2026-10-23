# Callbacks y estados reales de entrega — 22/10/2026

## Alcance implementado

`notification_statuses.py` almacena los callbacks del webhook en
`whatsapp_delivery_receipts`, dentro de la SQLite de chat. La escritura se confirma
antes del ACK; la proyeccion posterior y un ciclo al arrancar/cada 5 s correlacionan
el mensaje y su destinatario con avisos de chat o voz. No crean conversaciones ni
invocan herramientas, LLM o envios de WhatsApp.

Cada aviso e intento distingue `accepted` de `sent`, `delivered`, `read` y `failed`.
`api_accepted_at` conserva la aceptacion aunque un callback posterior confirme un
fallo. `delivery_status_at` usa la fecha de Meta. La migracion no infiere entrega
o lectura a partir del HTTP de envio.

La clave canonica deduplica ID, destinatario normalizado, estado, fecha, codigos
seguros y cuenta emisora cuando exista. El inbox conserva el historial, no el
texto crudo de errores. La proyeccion exige ID y destinatario; un ID desconocido,
un match ambiguo o una respuesta perdida quedan pendientes hasta poder correlacionar.

## Orden y carreras

- La evidencia efectiva progresa por `read`, `delivered`, `failed`, `sent`,
  `accepted`, en ese orden de fuerza. La entrega/lectura no retrocede por un
  fallo contradictorio o un `sent` atrasado; el hecho original permanece registrado.
- Un timestamp del mismo nivel tampoco retrocede con escritores concurrentes.
- El inbox liga el evento al canal/aviso/intento antes de proyectar en el destino.
  La actualizacion por destino y el ACK posterior son reaplicables tras reiniciar.
- Solo se marcan las claves del snapshot procesado; un callback nuevo que llegue
  durante la proyeccion permanece pendiente para otro ciclo.
- Un callback anterior al guardado de la respuesta se resuelve cuando aparece el
  ID. Si se perdio la respuesta, una conciliacion con el ID recuperado permite
  aplicar callbacks ya almacenados. No se adivina el ID por numero de telefono.
- Los intentos antiguos conservan su historial sin cambiar el intento actual.

Un fallo del intento actual integra una sola vez la espera o bloqueo existentes,
sin borrar ID o aceptacion. Los fallos duplicados no incrementan el contador ni
desplazan su fecha. Las aceptaciones intermedias de API conservan la espera
exponencial acumulada; una entrega/lectura confirmada la reinicia y cancela el
reintento pendiente del intento actual.

## Rutas y aislamiento

El webhook procesa `statuses` incluso sin mensajes y admite envelopes mixtos.
Un callback valido se guarda antes de responder; un fallo de esa escritura da
HTTP 503. Una proyeccion temporalmente indisponible no pierde el recibo ya guardado
y se retoma desde la bandeja.

La base de voz se abre directamente y solo se migra su bandeja compartida. No se
arrancan sesiones ni se crean tablas de pacientes. La utilidad de conciliacion se
adapto igualmente para preservar esa exclusividad. Los callbacks de respuestas al
paciente se identifican como tales, sin actualizar el aviso al doctor aunque ambos
roles usen el mismo numero.

## Verificacion ejecutable

Los bucles iniciales reprodujeron ausencia de un estado `accepted` separado y la
perdida de espera exponencial entre fallos asincronos separados por HTTP aceptados.
Ambos casos pasaron despues de sus cambios correspondientes.

Suite completa final ejecutada despues de sincronizar fuentes y SDD:
**553 pruebas, OK**, en 85,721 s.

```sh
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes asaek@192.168.1.12 \
  'env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo/tests:/home/asaek/Downloads/chatbot_test_repo /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -B -c '\''import os,unittest; os.chdir("/home/asaek/Downloads/chatbot_test_repo"); result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover("tests")); raise SystemExit(not result.wasSuccessful())'\'''
```

Casos comprobados con dobles, relojes controlados y SQLite temporal:

- HTTP aceptado seguido de `failed/131047`, conservando ID y aceptacion y deteniendo
  reintentos con la misma configuracion.
- Lectura/entrega/envio fuera de orden, callbacks duplicados y timestamp atrasado.
- Callback dentro del envio, antes de devolver el ID, y recuperacion tras reabrir.
- ID no recuperado, destinatario incorrecto, aliases mexicanos y match ambiguo.
- Dos carreras de proyeccion: un evento nuevo durante el ACK y una actualizacion
  mas reciente que adelanta a un snapshot anterior.
- Callback de voz por el webhook, con spies que comprueban cero llamadas de
  conversacion y cero envios salientes.
- Destino bloqueado o proyeccion indisponible despues de persistir; recuperacion
  posterior sin exigir otro webhook.
- Error de escritura en el inbox y HTTP 503 en vez de ACK falso.
- Callback de intento antiguo que no modifica el nuevo, y espera acumulada ante
  varios fallos asincronos.
- Conciliacion real de la utilidad sobre una base temporal de voz, reapertura sin
  tablas de pacientes y correlacion del ID recuperado.
- Callback de confirmacion al paciente que no afecta al aviso del doctor en la
  prueba con numero compartido.
- Ciclo de lifespan que recupera un callback temprano sin otro POST.
- Historicos actualizables por ID sin inventar intentos, y migracion que solo
  atribuye aceptacion cuando habia un ID registrado.

Los callbacks sinteticos se limitaron a las bases temporales; no se fabricaron
estados en las bases operativas para declarar una entrega real.

## Raspberry y configuracion

- Fuentes/SDD sincronizados y `.env` completo copiado; igualdad byte por byte en
  memoria y modo `600` comprobados.
- Sin unidad systemd del proyecto ni sesion de laboratorio activa al recargar.
- Se verificaron PID, comando y directorio, y se espero salida y puerto libre.
- Backend: PID `198807` reemplazado por `259675`, puerto 8000.
- Laboratorio: PID `198874` reemplazado por `259739`, puerto 8001.
- Valores administrados de ambos procesos iguales a `.env`; transporte `template`,
  nombre, idioma y componentes reales vacios.
- Ngrok PID `22863` conservado.
- Migracion de entrega aplicada en ambas bases, conservando 47 avisos de chat y
  1 de voz. Chat conserva 42 como `accepted` y 5 sin estado de entrega acreditado;
  voz conserva 1 como `accepted`. Ninguno se migro como entregado o leido.
- Las auditorias historicas siguen con cero intentos inventados y el inbox operativo
  tiene cero callbacks registrados al comprobar. La base de voz no contiene
  `patients` ni la bandeja central de callbacks.
- Registros de arranque sin errores de recuperacion o proyeccion.

| Ruta | Directa en Raspberry | Publica por ngrok |
| --- | --- | --- |
| `GET /` | 200 y cuerpo esperado | 200 y cuerpo esperado |
| `GET /webhook/whatsapp` | 200 y challenge correcto | 200 y challenge correcto |
| `POST /webhook/whatsapp`, evento vacio | 200 y cuerpo esperado | 200 y cuerpo esperado |

`GET /lab/health` devolvio 200, estado `ok`, audio `realtime`. Los checks no crearon
gestiones ni enviaron mensajes de WhatsApp.

## Limite de verificacion real

La consulta autenticada del recurso del numero (`fields=id`) sigue devolviendo
HTTP `401`, codigo `190`, subcodigo `463`: el token de envio esta vencido. La
recepcion/proyeccion esta implementada y activa, pero no se acredita una nueva
entrega con Meta real. La prueba end-to-end requiere credenciales vigentes y
la plantilla real aprobada con su mapeo; la migracion no sustituye ese resultado.
