# Local to raspberry y cierre de autenticacion de WhatsApp

## Estado

8 de octubre de 2026. Sincronizacion, copia completa de configuracion, recarga y
verificacion completadas. El token del `.env` local actualizado paso la consulta
autenticada de solo lectura a Meta con HTTP 200. Queda cerrado el pendiente de
autenticacion del incremento 018.

## Sincronizacion

El dry-run inicial no encontro archivos de proyecto pendientes en el mirror.
Se ejecuto igualmente la sincronizacion, preservando datos de ejecucion y
excluyendo `.git`, `.venv`, caches y `.env` del paso masivo.

El paso dedicado reemplazo el `.env` remoto con el archivo local completo. La
comparacion en memoria confirmo igualdad byte por byte y modo `600`, sin imprimir
valores ni hashes. La evidencia y los estados del SDD se actualizaron solamente
en el checkout local y despues se sincronizaron al mirror.

## Runtime

La inspeccion no encontro unidades systemd de sistema/usuario para el proyecto.
El PID `298437` era el listener Uvicorn verificado de `127.0.0.1:8000`, con el
comando y directorio del proyecto. Se termino solamente ese PID mediante SIGTERM
y se recargo de PID `298437` a `384300`, con valores frescos del `.env` copiado.
El nuevo listener y su configuracion efectiva fueron comprobados; la comparacion
incluyo las credenciales sin mostrarlas.

Ngrok continuo con PID `67420`. Los cambios de evidencia documental se incluyen
en la sincronizacion final y la recarga requerida por la misma solicitud.

## Verificacion

Se usaron `curl` en la Raspberry y configuracion por entrada estandar para evitar
secretos en argumentos y salida. Cada ruta devolvio HTTP 200 y el cuerpo esperado.
Los POST enviaron eventos vacios y la consulta de Meta fue de solo lectura.

```text
FULL_ENV_CHECK: byte_for_byte_match=true, mode=0o600
RESTART: effective_env_matches=true
local  GET /                 -> 200, {"status":"ok"}
local  GET /webhook/whatsapp  -> 200, desafio esperado
local  POST /webhook/whatsapp -> 200, {"status":"ok"}
public GET /                 -> 200, {"status":"ok"}
public GET /webhook/whatsapp  -> 200, desafio esperado
public POST /webhook/whatsapp -> 200, {"status":"ok"}
Meta   GET phone resource   -> 200, autenticacion valida
```

La verificacion comprueba rutas, configuracion efectiva y credenciales aceptadas
por Meta; no envio mensajes de prueba ni repitio acciones de agenda. Las 308
pruebas del incremento 018 ya habian pasado en la Raspberry y el codigo no cambio
durante esta solicitud de despliegue.
