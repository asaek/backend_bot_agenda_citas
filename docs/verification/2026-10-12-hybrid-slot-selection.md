# Seleccion hibrida de horarios - 12/10/2026

## Resultado

Funcionalidad implementada y verificada; backend actualizado en Raspberry Pi.
El cierre operativo quedo completado el 13/10/2026, con configuracion actualizada,
reinicio y autenticacion Meta HTTP 200. Se conserva abajo la evidencia historica
del bloqueo inicial por token expirado y la comprobacion que lo resolvio.

## Reproduccion y solucion

La regresion del servicio reproduce la cita de hoy a las 4 PM, la solicitud
`quisiera cambiar esa cita para ma;ana` y las respuestas `a las 9 am estaria bien`
y `si a las 9 am esta bien`. Antes del cambio, ambas devolvian `No identifiqué una
hora de la lista`. Despues, cada una prepara la confirmacion en su primer turno;
la cita conserva fecha, hora y motivo hasta recibir `si confirmo`.

Se amplio la via local y se agrego un evaluador estructurado para expresiones no
reconocidas, con referencias efimeras a slots y evidencia literal. Se comparte una
sola interpretacion entre pausa, router y seleccion. El modelo usa modo texto sin
herramientas, no recibe identificadores de cita/paciente ni el motivo y no ejecuta
mutaciones. Fallos del proveedor y respuestas invalidas conservan la gestion y
registran solo metadata segura.

## Pruebas en Raspberry Pi

Las regresiones cubren expresiones naturales, ordinales, reinicio, pausa,
expiracion, fallos HTTP, tool calls inesperadas, JSON invalido, referencias
inventadas, evidencia ausente, hora numerica incompatible, condiciones, dos
opciones y AM/PM incompleto. Las afirmaciones aisladas no seleccionan una hora.
Se distinguen cantidades (`dos horarios`) de horas y representaciones equivalentes
(`las nueve (9 am)`) de dos opciones con minutos o periodos diferentes.

El webhook verifica que duplicar la seleccion no llama otra vez al evaluador y
duplicar la confirmacion modifica una sola cita y notifica una sola vez al doctor.
Los fallos HTTP del evaluador se registran una vez incluso al repetir el webhook.

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -m unittest discover -s /home/asaek/Downloads/chatbot_test_repo/tests -q
Ran 389 tests in 29.634s
OK
SYNTAX_OK 56 files
```

Las pruebas usan SQLite temporal, agenda falsa y cliente WhatsApp falso.
Una comprobacion adicional con el proveedor de IA configurado interpreto
`Sí, ese de las nueve me queda perfecto` y `Me quedo con el primero de la mañana`
contra tres horarios sinteticos, seleccionando el slot esperado en ambos casos.
Esa comprobacion no accedio a la agenda real ni envio mensajes.

## Revision

### Standards

La revision detecto validacion omitida de horas numericas invalidas, perdida de
metadata de errores y despacho duplicado entre estados activos/pausados. Se
corrigieron mediante validacion previa, registro existente de fallos y despacho
compartido. La representacion redundante de una hora conserva la via natural.

### Spec

La revision detecto alternativas mezclando digitos y palabras, y deduplicacion
que perdia minutos o AM/PM. Las regresiones reprodujeron esos casos antes de la
correccion. La comparacion final reutiliza el patron de horas y conserva minutos
y periodos completos; las regresiones y la suite final pasan.

## Runtime

Se sincronizaron codigo y SDD antes de cada ejecucion. Se copio el `.env` completo
sin imprimir valores; la comparacion byte por byte fue positiva y el modo es `600`.
No se encontro una unidad systemd del proyecto. Se verificaron puerto, proceso y
directorio antes de reemplazar el listener Uvicorn desde la raiz del mirror.

```text
ENV_FILE_MATCH True MODE 0o600
BACKEND 687917 -> 815865 RUNTIME_ENV_MATCH True
NGROK_EXISTING 5146
local  GET /                 -> 200, cuerpo esperado
local  GET /webhook/whatsapp  -> 200, desafio esperado
local  POST /webhook/whatsapp -> 200, {"status":"ok"}
public GET /                 -> 200, cuerpo esperado
public GET /webhook/whatsapp  -> 200, desafio esperado
public POST /webhook/whatsapp -> 200, {"status":"ok"}
META_AUTH -> 401, code 190, subcode 463
```

Los POST fueron eventos vacios. La comprobacion Meta fue un GET autenticado de
solo lectura al recurso del numero configurado. El token de envio expiro; las
rutas de webhook saludables no acreditan que WhatsApp permita enviar mensajes.

## Bloqueo operativo inicial

Actualizar `WHATSAPP_ACCESS_TOKEN` en el `.env` local con un token vigente y
repetir el flujo de copia completa, igualdad/modo, reinicio y verificaciones.
La fuente de configuracion sigue siendo el checkout local; no editar el mirror.

## Cierre de local to raspberry - 13/10/2026

La solicitud posterior `local to raspberry` sincronizo el proyecto completo y
reemplazo el `.env` del mirror con el archivo local actualizado. Se comprobo
igualdad byte por byte y modo `600`, sin imprimir valores ni hashes. El proyecto
ya estaba sincronizado; las pruebas funcionales previas siguen siendo aplicables
porque no hubo cambios al codigo de la aplicacion.

No se encontraron unidades systemd del proyecto. Antes del reinicio se verificaron
listener, comando y directorio de Uvicorn. El nuevo proceso cargo los valores
actualizados, eliminando exports anteriores de las claves gestionadas. Se mantuvo
el ngrok existente.

```text
ENV_FILE_MATCH True MODE 0o600
BACKEND 815865 -> 2091802 RUNTIME_ENV_MATCH True
NGROK_EXISTING 5146
local  GET /                 -> 200, cuerpo esperado
local  GET /webhook/whatsapp  -> 200, desafio esperado
local  POST /webhook/whatsapp -> 200, {"status":"ok"}
public GET /                 -> 200, cuerpo esperado
public GET /webhook/whatsapp  -> 200, desafio esperado
public POST /webhook/whatsapp -> 200, {"status":"ok"}
META_AUTH -> 200, recurso esperado
```

La comprobacion Meta fue un GET de solo lectura y los POST fueron eventos vacios.
El token actualizado es valido y queda resuelto el bloqueo de autenticacion.
