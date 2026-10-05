# Verificacion de horarios disponibles para reprogramar

## Fecha

5 de octubre de 2026.

## Cambio

Antes de pedir confirmacion para reprogramar una cita, el backend consulta los horarios
libres de todo el dia destino y los muestra en WhatsApp. Conserva la cita, la llamada y
los horarios ofrecidos durante 10 minutos. Solo una hora de esa lista puede avanzar a la
confirmacion; una seleccion fuera de la lista no modifica la cita. La modificacion sigue
requiriendo confirmacion explicita.

## Verificacion automatizada en Raspberry Pi

Comando ejecutado:

```text
PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -m unittest discover -s /home/asaek/Downloads/chatbot_test_repo/tests -q
```

Resultado: `Ran 216 tests ... OK`.

Las regresiones comprueban que se muestran los horarios del dia destino, que una hora no
ofrecida no crea una confirmacion y que la seleccion valida requiere confirmacion antes
de modificar la cita.

## Runtime en Raspberry Pi

Uvicorn se reinicio despues de sincronizar los archivos; el PID verificado paso de
`2893242` a `2920636`. El tunel ngrok permanecio activo con PID `19472`.

| Ruta | Resultado local | Resultado publico |
| --- | --- | --- |
| `GET /` | `200 {"status":"ok"}` | — |
| `GET /webhook/whatsapp` | `200 12345` | `200 12345` |
| `POST /webhook/whatsapp` (evento sin mensajes) | `200 {"status":"ok"}` | `200 {"status":"ok"}` |

No se enviaron mensajes reales ni se modificaron citas de Google durante la verificacion.
