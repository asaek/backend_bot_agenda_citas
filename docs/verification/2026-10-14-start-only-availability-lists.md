# Disponibilidad con solo la hora de inicio - 14/10/2026

## Resultado

Listas de disponibilidad actualizadas y verificadas en Raspberry Pi. Cada opcion
presenta solo el inicio como `- h:mm AM/PM`, tanto al agendar y reprogramar como al
retomar una lista pausada. ADR 0051 registra la decision.

## Cambios

- `format_availability_reply()` omite la hora de fin en la lista.
- `_resumed_workflow_prompt()` aplica la misma regla a slots persistidos.
- `SYSTEM_PROMPT` solicita solo el inicio para disponibilidad.
- Las comprobaciones existentes comparan lineas completas para detectar rangos
  accidentales y conservar la comprobacion de horarios ocupados.
- Los slots de herramientas y estado persistido conservan inicio y fin ISO.

## Pruebas en Raspberry Pi

Codigo y SDD sincronizados antes de ejecutar las comprobaciones. La suite se
ejecuto desde `/home/asaek/Downloads/chatbot_test_repo`, con SQLite temporal y
proveedores falsos para evitar operaciones externas:

```text
PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests
CALENDAR_PROVIDER=fake CALENDAR_AVAILABILITY_PROVIDER=fake
DOCTOR_NOTIFICATIONS_ENABLED=false
.venv/bin/python -m unittest discover -s tests -q
Ran 389 tests in 29.668s
OK
```

La suite cubre seleccion de horarios, reprogramacion, slots ocupados, pausa y
reinicio. Una comprobacion adicional con slots sinteticos reprodujo las nueve
opciones solicitadas por el usuario, convirtiendo desde UTC a la zona de agenda:

```text
Horarios disponibles para el 14/10/2026:
- 9:00 AM
- 9:30 AM
- 10:00 AM
- 10:30 AM
- 11:00 AM
- 11:30 AM
- 12:00 PM
- 12:30 PM
- 1:00 PM
```

Se comprobo la deduplicacion entre calendarios, `12:00 AM` para medianoche,
`12:00 PM` para mediodia y que la normalizacion WhatsApp mantiene la lista.
Los horarios del ejemplo son sinteticos, no una consulta de la agenda real.

## Despliegue y configuracion

- Sincronizacion del proyecto sin `.git`, entornos virtuales, caches ni datos.
- Comprobacion de contenido del mirror mediante `rsync --checksum --dry-run`.
- Copia completa del `.env` local; igualdad byte por byte positiva y modo `600`,
  sin imprimir valores ni hashes.
- No habia unidad systemd del proyecto, listener en el puerto 8000 ni ngrok activo.
- Uvicorn iniciado desde la raiz del mirror, con la configuracion recien copiada;
  PID inicial `10175`, propietario verificado del puerto `127.0.0.1:8000`.
- Comparacion en memoria entre las variables del proceso y el `.env`: positiva.
- Tunel habitual de ngrok iniciado con PID `10223` y `--inspect=false`.

## HTTP y autenticacion

| Entorno | Comprobacion | Resultado |
| --- | --- | --- |
| Local | `GET /` | HTTP 200 y `{"status":"ok"}` |
| Local | `GET /webhook/whatsapp` | HTTP 200 y desafio esperado |
| Local | `POST /webhook/whatsapp` | HTTP 200 y `{"status":"ok"}` |
| Publico | `GET /` | HTTP 200 y `{"status":"ok"}` |
| Publico | `GET /webhook/whatsapp` | HTTP 200 y desafio esperado |
| Publico | `POST /webhook/whatsapp` | HTTP 200 y `{"status":"ok"}` |
| Meta | GET autenticado al recurso del numero con `fields=id` | HTTP 200 e ID coincidente |

Los POST enviaron eventos vacios. La comprobacion de Meta fue de solo lectura;
no se enviaron mensajes de WhatsApp ni se modificaron citas reales.
