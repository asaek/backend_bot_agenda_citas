# Formato de fecha en confirmaciones habladas — 21/10/2026

## Causa

`VoiceTools._propose()` construia la fecha de las preguntas de confirmacion como
`YYYY-MM-DD a las hh:mm AM/PM`. Esa forma mostraba el año antes del mes y del dia,
y ponia la fecha antes de la hora.

## Cambio

- La pregunta presenta primero la hora local de inicio en 12 horas con AM/PM y
  despues la fecha `DD/MM/YYYY`, por ejemplo `a las 10:00 AM del 19/10/2026`.
- La misma forma se usa para crear y cancelar, y para la cita anterior y el nuevo
  horario al reprogramar.
- Se reutiliza `format_patient_time()` para conservar AM/PM y evitar depender del
  locale del sistema.
- Una prueba de regresion comprueba la pregunta exacta para crear, reprogramar y
  cancelar. Antes del cambio fallo con la salida ISO observada.

## Verificacion en Raspberry Pi

Despues de sincronizar el codigo y la documentacion locales:

| Comprobacion | Resultado |
| --- | --- |
| Prueba focalizada `confirmation_prompts_present_time_before_mexican_date` | Correcta |
| `test_voice_tools.py` | 22 pruebas correctas |
| Suite completa `python -m unittest discover -s tests -q` | 469 pruebas correctas en 66.025 s |
| `GET /` | HTTP 200, `{"status":"ok"}` |
| `GET /webhook/whatsapp` con el token configurado | HTTP 200, challenge `12345` |
| `POST /webhook/whatsapp` con evento vacio | HTTP 200, `{"status":"ok"}` |
| `GET /lab/health` | HTTP 200, modo `realtime`, proveedor `google` |

Se verifico que no hubiera llamadas, mensajes ni acciones en curso. Sin unidad de
servicio del proyecto, se recargo solo el proceso del laboratorio Realtime despues
de confirmar el PID y el puerto: PID `871885` -> `1820114`. La salud posterior fue
correcta; el backend de WhatsApp y el tunel ngrok no se reiniciaron.
