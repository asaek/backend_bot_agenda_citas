# Cuota agotada de sesiones de voz — 20/10/2026

## Causa

El perfil de laboratorio habia consumido **5 de 5** sesiones Realtime. La cuota se
cuenta de forma durable en `voice_sessions`; reiniciar Uvicorn no crea un perfil
nuevo ni reinicia el contador. No habia llamadas activas, mensajes en proceso ni
acciones inciertas.

Los intentos recientes llegaron a `/lab/calls`, pero terminaron como
`negotiation_failed` antes de insertar otra sesion de voz y sin recibir frames. La
causa era `VoiceRepository.begin` rechazando la cuota; `CallingService` la convertia
en un error generico de audio. Por eso el navegador podia pedir el microfono y luego
parecer que el SDP o la conexion habia fallado.

La ruta WebRTC desde Chrome en el Mac se reprodujo con micrófono simulado y Realtime
falso: ICE `connected`, RTP de audio en ambos sentidos, un turno de voz y cero errores
JavaScript. Esta comprobacion no uso OpenAI ni Google.

## Cambio

`VoiceRepository.begin` ahora comunica una `VoiceSessionQuotaExceededError` con el
uso y maximo. `CallingService` finaliza los recursos y conserva el resultado seguro
`session_quota_reached`; `/lab/calls` responde HTTP **429** con el conteo y explica
que reiniciar no restablece la cuota. La pagina muestra ese mensaje; el limite sigue
siendo 5 y no se amplio.

La regresion se ejecuto en la Pi antes y despues del cambio:

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests \
  -p test_calling_lab.py -k voice_session_quota -v
Antes: FAIL — HTTP 422, fallo generico de audio.
Despues: 1 test OK — HTTP 429 y texto 1/1, sin crear otra sesion.
```

Despues se verifico la pagina real de laboratorio desde Chrome del Mac con un
microfono simulado. El estado visible contiene `5/5` y `Reiniciar no restablece`; la
sesion de voz permanece en 5, el intento queda `session_quota_reached` y no se abre
la conexion OpenAI ni se escribe en Google Calendar.

## Verificacion y despliegue

- Suite completa en la Pi: **465 tests en 63.901 s, OK**.
- El backend del laboratorio se reinicio solo tras comprobar que no habia llamadas
  ni sesiones activas.
- PID del laboratorio: `801482 -> 813149`; `audio_mode=realtime` y
  `calendar_provider=google`.
- `/lab/health` y `/lab` respondieron HTTP 200 desde la Pi y desde el Mac por el
  tunel SSH conservado.
- La interfaz sigue conectada al calendario Google del laboratorio; la cuota se
  mantiene sin cambios. No se hizo una reserva real ni se amplio el presupuesto.
