# Verificacion de enrutamiento entre flujos pendientes

## Fecha

5 de octubre de 2026.

## Cambio

`ConversationService` clasifica el mensaje entrante antes de procesar una fecha, horario,
datos de reserva o confirmacion pendiente. Una respuesta esperada continua; un abandono
limpia el estado sin afectar el calendario; una nueva intencion reemplaza el flujo
anterior; una cancelacion ambigua solicita aclaracion y conserva el estado. Las acciones
de cambio descartadas no pueden ejecutarse con una confirmacion posterior.

## Verificacion automatizada en Raspberry Pi

Comando ejecutado:

```text
PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -m unittest discover -s /home/asaek/Downloads/chatbot_test_repo/tests -q
```

Resultado: `Ran 231 tests ... OK`.

Las pruebas cubren el abandono de una reserva, el cambio desde disponibilidad a consulta
o cancelacion, la aclaracion de `cancela`, el descarte de una confirmacion de
reprogramacion antes de un `Si` tardio y la interrupcion del flujo con `Hola` o
`Olvida lo que estás haciendo, te estoy saludando`.

## Runtime en Raspberry Pi

Uvicorn se reinicio despues de sincronizar los archivos; el PID verificado paso de
`3174156` a `3191216`. El tunel ngrok permanecio activo con PID `19472`; no hay un unit
systemd del proyecto.

| Ruta | Resultado local | Resultado publico |
| --- | --- | --- |
| `GET /` | `200 {"status":"ok"}` | — |
| `GET /webhook/whatsapp` | `200 12345` | `200 12345` |
| `POST /webhook/whatsapp` (evento sin mensajes) | `200 {"status":"ok"}` | `200 {"status":"ok"}` |

No se enviaron mensajes reales ni se modificaron citas durante la verificacion.
