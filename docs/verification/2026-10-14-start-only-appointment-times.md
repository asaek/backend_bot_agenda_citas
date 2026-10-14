# Citas y confirmaciones con solo el inicio - 14/10/2026

## Resultado

El formato corto de disponibilidad se extendio a las citas reservadas, sus
detalles y las confirmaciones de cancelacion y reprogramacion. El backend esta
actualizado en Raspberry Pi. Decision: ADR 0052.

## Comportamiento verificado

El listado proporcionado por el usuario se comprobo con datos sinteticos:

```text
- Horario: 9:00 AM
  *Motivo de consulta:*
  Tengo problemas en la vista me van a revisar el queratocono
```

La confirmacion backend muestra:

```text
¿Confirmas que deseas cancelar esta cita?

Datos de la cita:
Fecha: 14/10/2026
Hora: 9:00 AM
Motivo: Tengo problemas en la vista me van a revisar el queratocono
```

La nueva fecha y hora de reprogramacion usa tambien AM/PM, por ejemplo
`Nueva fecha y hora: 14/10/2026 a las 1:00 PM.`. Se conserva la respuesta de
confirmacion explicita antes de modificar una cita.

## Pruebas en Raspberry Pi

Se sincronizaron codigo, comprobaciones y SDD antes de ejecutar desde la raiz del
mirror, con proveedores falsos y SQLite temporal:

```text
PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests
CALENDAR_PROVIDER=fake CALENDAR_AVAILABILITY_PROVIDER=fake
DOCTOR_NOTIFICATIONS_ENABLED=false
.venv/bin/python -m unittest discover -s tests -q
Ran 389 tests in 29.767s
OK
```

Las expectativas existentes se actualizaron para tablas, bloques, confirmaciones,
medianoche y mediodia. La suite verifica tambien la seleccion de la cita desde un
listado corto, reprogramacion y cancelacion con confirmacion, reinicios y
notificaciones unicas del webhook.

La comprobacion adicional verifico:

- Normalizacion de `Hora: 09:00 - 09:30` a `Hora: 9:00 AM`.
- Rangos con `a`, guion, en dash y em dash; aplicar de nuevo el formato es idempotente.
- Lectura de la hora inicial desde listados nuevos y rangos historicos.
- Conservacion del motivo incluso si su linea empieza por `Hora:` y contiene un rango.
- `12:00 AM`, `12:00 PM` y `1:00 PM` para medianoche, mediodia y tarde.
- Inicio unico en cancelacion y reprogramacion, conservando fin e identidad internos.

## Configuracion y runtime

Se copio el `.env` local completo: igualdad byte por byte positiva y modo `600`,
sin mostrar valores ni hashes. No se encontro una unidad systemd del proyecto.
La recarga del incremento reemplazo el PID verificado `14588` por `41143`, desde
`/home/asaek/Downloads/chatbot_test_repo`, con las variables recien leidas. Se
verificaron el directorio del proceso, la propiedad del puerto `127.0.0.1:8000`
y la igualdad en memoria entre configuracion del proceso y `.env`.
El tunel ngrok existente, PID `10223`, se conservo.

| Entorno | Comprobacion | Resultado |
| --- | --- | --- |
| Local | `GET /` | HTTP 200 y `{"status":"ok"}` |
| Local | `GET /webhook/whatsapp` | HTTP 200 y desafio esperado |
| Local | `POST /webhook/whatsapp` | HTTP 200 y `{"status":"ok"}` |
| Publico | `GET /` | HTTP 200 y `{"status":"ok"}` |
| Publico | `GET /webhook/whatsapp` | HTTP 200 y desafio esperado |
| Publico | `POST /webhook/whatsapp` | HTTP 200 y `{"status":"ok"}` |
| Meta | GET autenticado del numero con `fields=id` | HTTP 200 e ID coincidente |

Los POST fueron eventos vacios y la comprobacion Meta de solo lectura. Las
reproducciones usaron citas sinteticas, sin enviar WhatsApp ni modificar agenda real.
