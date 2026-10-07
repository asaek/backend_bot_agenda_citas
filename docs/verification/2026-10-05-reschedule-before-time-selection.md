# Verificacion de disponibilidad antes de pedir hora para reprogramar

## Fecha

5 de octubre de 2026.

## Cambio

Cuando el paciente pide cambiar la hora de una cita sin proponer una hora nueva,
`ConversationService` resuelve primero la cita mencionada a partir del listado reciente y
consulta todos los horarios libres de ese dia. Presenta la lista antes de solicitar una
seleccion; despues conserva la confirmacion explicita antes de mover la cita. Si no puede
identificar una unica cita, pide aclaracion en vez de elegir una arbitrariamente.

## Verificacion automatizada en Raspberry Pi

Comando ejecutado:

```text
PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -m unittest discover -s /home/asaek/Downloads/chatbot_test_repo/tests -q
```

Resultado: `Ran 236 tests ... OK`.

La regresion reproduce una cita listada para el dia siguiente seguida de `Quisiera
modificar esa cita y cambiar su hora`. Comprueba que el backend muestra la disponibilidad,
no llama al LLM para pedir una hora a ciegas, vincula la seleccion a la cita listada y
solo la mueve despues de una respuesta afirmativa.

## Runtime en Raspberry Pi

Uvicorn se reinicio despues de sincronizar los archivos; el PID verificado paso de
`262102` a `301370`. El tunel ngrok permanecio activo con PID `19472`.

| Ruta | Resultado local | Resultado publico |
| --- | --- | --- |
| `GET /` | `200 {"status":"ok"}` | — |
| `GET /webhook/whatsapp` | `200 12345` | `200 12345` |
| `POST /webhook/whatsapp` (evento sin mensajes) | `200 {"status":"ok"}` | `200 {"status":"ok"}` |

No se enviaron mensajes reales ni se modificaron citas durante la verificacion.
