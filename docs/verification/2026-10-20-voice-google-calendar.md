# Google Calendar para el laboratorio Realtime — 20/10/2026

## Causa observada

La confirmacion que motivo el diagnostico procedia del laboratorio Realtime. Ese
flujo usaba `FakeCalendarProvider`: la accion quedo persistida en la SQLite
exclusiva de voz, pero no hizo ninguna solicitud de escritura a Google Calendar.
El adaptador operativo de WhatsApp ya usaba Google; el laboratorio era una ruta
separada con una identidad ficticia.

La regresion minima de `VoiceTools._confirm` se ejecuto primero en la Pi:

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests \
  -p test_voice_tools.py -k successful_remote_provider_mutation -v
ERROR: AttributeError: appointments
```

La mutacion remota podia tener exito y luego fallar al guardar el resultado porque
el codigo exigia `.appointments`, atributo propio del proveedor fake. El resultado
no se podia completar de manera durable con un proveedor Google.

## Decision e implementacion

- Se conserva `VOICE_CALENDAR_PROVIDER=fake` por defecto para tests y desarrollo.
- El laboratorio Realtime activo usa `VOICE_CALENDAR_PROVIDER=google`, con los
  calendarios, credenciales y zona horaria ya configurados en la Pi.
- Los eventos usan `managed_by=whatsapp_voice_lab`; el backend de WhatsApp conserva
  `managed_by=whatsapp_chatbot` y no los muestra como citas de pacientes, aunque
  compartan calendario y el perfil de laboratorio use IDs ficticios.
- `VoiceTools` ya no necesita estado en memoria del fake para persistir una mutacion
  remota. En modo Google, Calendar conserva autoridad sobre disponibilidad y citas.
- `/lab/health` y el cliente HTML indican el proveedor activo y advierten que en
  modo Google las confirmaciones crean eventos reales.
- Las reservas falsas previas no se importan ni se vuelven a ejecutar. La
  verificacion no creo un evento real; una nueva reserva debe confirmarse desde
  `/lab` para aparecer en el calendario operativo.

## Verificacion en Raspberry Pi

Pruebas focalizadas posteriores a la correccion:

| Suite | Resultado |
| --- | --- |
| `test_voice_tools.py` | 19 correctas |
| `test_google_calendar_provider.py` | 18 correctas |
| `test_calling_lab.py` | 5 correctas |
| `test_voice_session.py` | 17 correctas |
| `test_lab_continuity.py` | 11 correctas |

Suite completa, desde `/home/asaek/Downloads/chatbot_test_repo`:

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -q
Ran 464 tests in 63.813s
OK
```

La prueba Chromium/WebRTC con Realtime falso se ejecuto sin APIs externas:

```text
~/.local/bin/uv run --no-project --with playwright==1.56.0 --with httpx \
  python scripts/verify_lab_controls.py
passed=true, javascript_errors=[], token_free_connection=true,
voice_text_shared_history=true, lost_response_retry_without_duplicate=true,
text_after_hangup_restores_context=true, external_api_calls=0
```

Google se comprobo con una consulta `freeBusy` de solo lectura: un calendario
configurado, una disponibilidad devuelta y cero eventos escritos. La suite HTTP
simulada cubre crear, listar, reprogramar y cancelar; un proveedor WhatsApp no puede
listar los eventos cuyo propietario sea el del laboratorio.

## Sincronizacion y runtime

- Se sincronizaron solo los archivos de esta integracion, pruebas, scripts de
  laboratorio y SDD; `rsync --dry-run` mostro exclusivamente esas rutas.
- Se transfirio unicamente `VOICE_CALENDAR_PROVIDER`; la comprobacion en memoria
  dio coincidencia y el `.env` remoto conserva modo `600`.
- No habia unidades systemd del proyecto. Se verificaron rutas, argumentos y
  puertos antes de terminar solo los procesos Uvicorn del proyecto sin sesiones
  activas.

| Proceso | PID previo | PID nuevo | Resultado |
| --- | ---: | ---: | --- |
| Backend de texto, puerto 8000 | 270424 | 759310 | `/` responde 200 y `{"status":"ok"}` |
| Laboratorio Realtime, puerto 8001 | 633510 | 759913 | `audio_mode=realtime`, `calendar_provider=google` |

El tunel ngrok PID 22863 y el tunel SSH local PID 8546 se conservaron. Desde la Pi
y desde el Mac, `/lab/health` y `/lab` responden 200 sin token; la pagina declara
`data-calendar-provider="google"` y mantiene `data-audio-mode="realtime"`.

| Comprobacion | Resultado |
| --- | --- |
| `GET /` local y publico | 200, `{"status":"ok"}` |
| `GET /webhook/whatsapp` local y publico | 200, challenge correcto |
| `POST /webhook/whatsapp` vacio, local y publico | 200, `{"status":"ok"}` |
| Meta Graph `GET` de solo lectura, `fields=id` | 401, codigo 190/subcodigo 463; token de envio vencido |

No se imprimieron credenciales ni se hizo una mutacion real de Google Calendar.
