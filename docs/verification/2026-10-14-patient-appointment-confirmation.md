# Confirmacion al paciente con bloques compartidos - 14/10/2026

## Alcance y resultado

El usuario eligio que la confirmacion incluya solo cita y paciente. La respuesta
posterior a crear, reprogramar o cancelar usa `appointment_messages.py`, compartido
con la notificacion del doctor. El resumen y la prioridad son internos.

El paciente recibe fecha `DD/MM/YYYY` y solo el inicio con AM/PM. El estado proviene
del resultado real del proveedor: por ejemplo, `programada` para `scheduled` y
`confirmada` para `confirmed`. El nombre completo se carga de persistencia.

## Pruebas ejecutadas en Raspberry Pi

Se sincronizaron fuente, comprobaciones y SDD antes de ejecutar desde el mirror:

```text
PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests
CALENDAR_PROVIDER=fake CALENDAR_AVAILABILITY_PROVIDER=fake
DOCTOR_NOTIFICATIONS_ENABLED=false
.venv/bin/python -m unittest discover -s tests -q
Ran 392 tests in 30.751s
OK
```

Las tres comprobaciones integradas nuevas verifican:

- `tengo vision borrosa` despues del horario y nombre produce los bloques
  completos, con una cita, un evento y cero llamadas adicionales al LLM.
- Reprogramar y cancelar muestran la cita definitiva y su estado, despues de
  confirmar la accion exacta; las preguntas previas no usan el encabezado de exito.
- Un proveedor que devuelve `2026-10-10T05:00:00Z` se muestra al paciente como
  `09/10/2026`, `11:00 PM`, en `America/Mexico_City`.

Ejemplo comprobado con agenda falsa:

```text
CONFIRMACION DE CITA
Tipo de evento: Cita agendada

CITA
Fecha: 09/10/2026
Hora: 9:00 AM
Motivo: tengo vision borrosa
Estado: programada

PACIENTE
Nombre: Asael Ponce Silva
Telefono: 1100000000
```

Se adapto la regresion del webhook con fallo de conexion en la primera entrega:
el segundo intento usa exactamente el cuerpo preparado en `reply_outbox`, crea
una sola cita y entrega una sola notificacion al doctor. Los campos comunes se
comparan entre ambos mensajes. Solo se genera el resumen ya previsto para el doctor.

Las pruebas del compositor mantienen su formato/saneamiento y comprueban que
tanto el encabezado nuevo como los cierres antiguos cortan la gestion anterior,
sin heredar sintomas. Las demas regresiones conservan los controles de nombre,
motivo, seleccion, confirmacion y reintentos.

## Sincronizacion y runtime

- Proyecto sincronizado y comprobado con `rsync --checksum --dry-run`.
- `.env` local completo copiado, igualdad byte por byte positiva y modo `600`.
- No habia unidad systemd del proyecto; se verifico el listener Uvicorn y su directorio.
- Recarga del incremento: PID `382273 -> 417237`, desde la raiz del mirror.
- Configuracion efectiva del proceso igual al `.env`; PID propietario de `127.0.0.1:8000`.
- Tunel ngrok existente conservado, PID `10223`.
- Sin valores secretos ni hashes en la evidencia.

| Entorno | Ruta o recurso | Resultado |
| --- | --- | --- |
| Local | `GET /` | 200 y `{"status":"ok"}` |
| Local | `GET /webhook/whatsapp` | 200 y desafio esperado |
| Local | `POST /webhook/whatsapp` | 200 y `{"status":"ok"}` |
| Publico | `GET /` | 200 y `{"status":"ok"}` |
| Publico | `GET /webhook/whatsapp` | 200 y desafio esperado |
| Publico | `POST /webhook/whatsapp` | 200 y `{"status":"ok"}` |
| Meta | GET del recurso del numero con `fields=id` | 200 e ID coincidente |

Los POST fueron eventos vacios; el GET autenticado de Meta fue de solo lectura.
Las regresiones usan proveedores falsos, sin mensajes ni cambios de agenda reales.
