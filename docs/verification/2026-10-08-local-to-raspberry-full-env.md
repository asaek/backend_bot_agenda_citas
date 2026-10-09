# Verificacion de copia completa de .env en local to raspberry

## Fecha y estado

8 de octubre de 2026. Flujo actualizado y ejecutado en el mirror Raspberry Pi.
La solicitud ordinaria incluye `.env` completo por defecto; skill, `AGENTS.md`,
README y SDD describen el mismo alcance.

## Reproduccion y copia

Antes del cambio, la comprobacion en memoria del archivo completo local y remoto
fallo, aunque el token individual ya se habia actualizado:

```text
FULL_ENV_CHECK {'byte_for_byte_match': False, 'mode': '0o600'}
```

Se sincronizaron primero los archivos del proyecto y despues se ejecuto el paso
dedicado de configuracion:

```text
rsync --archive --compress --ignore-times --chmod=u=rw,go= --itemize-changes ./.env asaek@192.168.101.19:~/Downloads/chatbot_test_repo/.env
FULL_ENV_CHECK {'byte_for_byte_match': True, 'mode': '0o600'}
```

La comparacion envio los bytes locales por entrada estandar de SSH y los comparo
con el archivo remoto en memoria. El comando utiliza permisos simbolicos porque
el openrsync de macOS rechazo las variantes numericas `F600` y `600`; la variante
simbolica fue ejecutada y produjo modo `600`. La copia conserva el archivo completo
en vez de mezclar claves, y `--ignore-times` fuerza la transferencia aun sin cambios
de tamano/timestamp. `.env` sigue excluido de Git por `.gitignore`.

## Runtime

Se inspeccionaron unidades systemd de sistema/usuario, proceso, directorio y puerto.
El Uvicorn manual verificado se reinicio de PID `190719` a `205406`, desde
`/home/asaek/Downloads/chatbot_test_repo`, con el comando estandar. Se limpiaron las
claves gestionadas y se proporcionaron todos los valores frescos leidos de `.env`.
La comparacion en memoria de la configuracion efectiva paso:

```text
FULL_RUNTIME_CONFIG_MATCHES_PI_ENV True
```

Ngrok permanecio activo con PID `67420`. La skill tambien exige recarga para una
sincronizacion sin cambios de codigo y describe los alcances explicitos de exclusion
de `.env`, una sola variable y sincronizacion sin reinicio.

## HTTP y autenticacion

```text
local  GET /                 -> 200, {"status":"ok"}
local  GET /webhook/whatsapp  -> 200, desafio esperado
local  POST /webhook/whatsapp -> 200, {"status":"ok"}
public GET /                 -> 200, {"status":"ok"}
public GET /webhook/whatsapp  -> 200, desafio esperado
public POST /webhook/whatsapp -> 200, {"status":"ok"}
Meta   GET phone resource   -> 200, autenticacion valida
```

Los POST usaron eventos vacios. La consulta de Meta fue de solo lectura y uso la
version de Graph API del cliente. Las comprobaciones no enviaron mensajes reales
ni repitieron acciones de agenda. No se imprimieron valores ni hashes de secretos.
`git diff --check` paso.
