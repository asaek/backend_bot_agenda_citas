# Limite de cinco minutos para llamadas Realtime — 2026-10-20

El maximo de la llamada Realtime pasa de 120 a 300 segundos (cinco minutos), a
peticion del usuario. El valor aplica como default de `RealtimeSettings`, como
fallback de `VOICE_MAXIMUM_SECONDS` y como ejemplo de `.env.example`. La clave
local y la del mirror no estaban definidas; el runtime toma este nuevo default.

Se mantienen los limites independientes: hasta 30 s sin actividad real, cinco
sesiones por perfil y 600 s como maximo configurado para el supervisor general
del laboratorio. El incremento afecta duracion maxima de una sesion, no concurrencia.

Verificacion de configuracion: `RealtimeSettings.from_environment` da 300 s sin
override y respeta `VOICE_MAXIMUM_SECONDS=300`; una prueba de la factory comprobo
que `CallingService.maximum_seconds` queda en 300 s. Pasaron las tres pruebas de
`test_realtime_provider.py` y la prueba focalizada de `test_lab_continuity.py`.

La Raspberry no define `VOICE_MAXIMUM_SECONDS` en `.env`; se removio cualquier
override heredado y el nuevo proceso uso el default de codigo de 300 s. Se reinicio
solo el laboratorio, sin sesiones activas:

| Proceso | PID previo | PID nuevo | Maximo efectivo | Inactividad |
| --- | --- | --- | --- | --- |
| Laboratorio Realtime, loopback 8001 | 270508 | 563829 | 300 s | 30 s |

`GET /lab/health` devolvio `{"status":"ok","mode":"laboratory","audio_mode":"realtime"}`;
`GET /lab` y `/lab/history` dieron HTTP 200 en la Pi. La pagina y salud tambien
respondieron HTTP 200 por el forwarding SSH en `http://localhost:8001`. No se
inicio llamada ni se invoco OpenAI durante la verificacion.
