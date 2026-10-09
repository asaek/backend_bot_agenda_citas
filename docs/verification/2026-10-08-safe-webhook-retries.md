# Verificacion de reintentos seguros del webhook

## Estado

8 de octubre de 2026. Codigo implementado, suite completa verificada en la
Raspberry Pi y backend recargado. Health y ambos metodos de webhook, locales y
publicos, pasan. La primera comprobacion encontro un token vencido (Meta HTTP
401, 190/463). Una solicitud posterior `local to raspberry` copio el `.env`
actualizado, recargo el runtime y obtuvo HTTP 200 en la autenticacion; ese
pendiente queda cerrado segun `2026-10-08-local-to-raspberry-retry-auth-recovery.md`.

## Incidente y reproduccion

La conversacion de prueba tenia una cita confirmada a las 11:02. A las 11:05:37
se creo otra solicitud de nombre con `source_message_id=385`, correspondiente a
un saludo recibido a las 9:31:52. La inspeccion de SQLite fue de solo lectura.
El reintento de Meta tras los fallos por token vencido es el disparador mas
probable; el runtime anterior no conservaba los logs HTTP necesarios para
confirmar esa solicitud concreta.

Antes de cambiar el codigo se sincronizaron cinco regresiones y se ejecutaron
en la Raspberry. Todas fallaron:

```text
reintento vigente: llamadas al LLM 2 != 1
reintento antiguo tras confirmar cita: envios 5 != 4
servicio recreado: llamadas al nuevo LLM 1 != 0
duplicados simultaneos: envios 2 != 1
contexto del turno: incluia mensajes y respuesta posteriores
Ran 5 tests in 0.402s
FAILED (failures=5)
```

## Verificacion automatizada

Despues de sincronizar codigo, pruebas y SDD se ejecuto la suite completa desde
la raiz del mirror, usando `unittest discover -s tests -q`. El lanzador fijo
`DATABASE_PATH=:memory:`, ambos proveedores de calendario `fake`, notificaciones
deshabilitadas por defecto y `LLM_PROVIDER=groq`. Las pruebas integradas inyectan
clientes falsos, configuracion de prueba y SQLite temporal; no consumen APIs ni
envian WhatsApp reales.

```text
Ran 308 tests in 10.636s
OK
```

La cobertura agregada verifica el caso original sin cambios de contexto ni otra
cita, recuperacion del texto fallido tras recrear el servicio, duplicados
simultaneos, exclusion por paciente con paralelismo entre pacientes distintos,
respuesta preparada antes del envio, respuestas historicas sin bandeja, resultado
incierto tras timeout, procesamiento interrumpido, cancelacion y liberacion del
bloqueo, preservacion del evento al doctor sin repetir la cita, y migracion
aditiva sin reescribir mensajes ni inventar intentos historicos.

`git diff --check` paso. La revision del incremento comprobo el uso de repositorios
para SQL, la conservacion de los estados existentes de `messages`, la separacion
entre procesamiento y envio, los eventos persistidos y los limites de un solo
proceso descritos en ADR 0047. Los cambios previos del checkout se conservaron.

## Despliegue y persistencia

Se sincronizaron los archivos excluyendo `.git`, `.venv`, caches y datos de
ejecucion. Se copio `.env` completo por el paso dedicado, comprobando igualdad
byte por byte en memoria y modo `600`, sin imprimir valores ni hashes.

No se encontraron unidades systemd del proyecto. Se verificaron el listener,
comando y directorio del Uvicorn manual y se recargo de PID `210050` a `290613`.
El nuevo proceso escucho en `127.0.0.1:8000` desde la raiz del mirror y su
configuracion efectiva coincidio con `.env`. Ngrok permanecio con PID `67420`.
Los logs del backend nuevo se anexan a `data/backend.log`.

La base existente contiene `reply_outbox` y `reply_delivery_attempts`.
`PRAGMA quick_check` devolvio `ok`, `foreign_key_check` no encontro problemas y
la cita historica `13` siguio en `confirmed`. No se reprodujeron mensajes antiguos
contra la conversacion real ni se modificaron sus datos para hacer pasar pruebas.

## Rutas y bloqueo externo en la primera comprobacion

Las comprobaciones usaron `curl` en la Raspberry. Los secretos se pasaron por
configuracion de entrada estandar, fuera de argumentos y salida. Los POST usaron
eventos vacios.

```text
local  GET /                 -> 200, cuerpo esperado
local  GET /webhook/whatsapp  -> 200, desafio esperado
local  POST /webhook/whatsapp -> 200, cuerpo esperado
public GET /                 -> 200, cuerpo esperado
public GET /webhook/whatsapp  -> 200, desafio esperado
public POST /webhook/whatsapp -> 200, cuerpo esperado
Meta   GET phone resource   -> 401, code=190, error_subcode=463
```

## Cierre del pendiente

La solicitud posterior `local to raspberry` transfirio el `.env` completo local
actualizado, comprobo igualdad y modo `600`, recargo el backend y verifico
configuracion, rutas y autenticacion de Meta con HTTP 200. La evidencia esta en
`2026-10-08-local-to-raspberry-retry-auth-recovery.md`. La correccion de reintentos
no renueva credenciales de Meta; la recuperacion provino de la configuracion
actualizada por el usuario.
