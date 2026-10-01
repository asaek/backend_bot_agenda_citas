# Verificacion del nombre en cada cita nueva

## Fecha

1 de octubre de 2026.

## Alcance

Verificar que cada solicitud nueva de cita pide el nombre completo aunque ya exista
en `patients.name`, actualiza ese valor antes de preguntar el motivo y mantiene el
horario pendiente. El reintento del mismo mensaje con el nombre debe repetir la
pregunta por el motivo sin crear una cita. Los estados pendientes anteriores a esta
regla conservan su comportamiento previo.

## Verificacion automatizada

- [x] La regresion del paciente con nombre registrado fallo antes del cambio porque
      recibió directamente la pregunta por el motivo.
- [x] El flujo solicita el nombre, actualiza el nombre guardado y luego solicita el
      motivo.
- [x] Un reintento del mensaje del nombre no crea una cita ni cambia el paso pendiente.
- [x] Una solicitud pendiente anterior a la regla conserva el flujo asociado al nombre registrado.
- [x] Los flujos de motivo invalido, aclaracion, evaluacion estructurada, reinicio y
      seleccion de horario pasan con el paso de nombre incluido.
- [x] La suite completa en el mirror de Raspberry Pi paso con `205` pruebas.

Comando ejecutado en el mirror:

```text
PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -m unittest discover -s /home/asaek/Downloads/chatbot_test_repo/tests -v
```

Resultado: `Ran 205 tests ... OK`.

## Verificacion HTTP en Raspberry Pi

Despues de sincronizar los cambios y reiniciar el proceso Uvicorn, se verifico el
backend activo en `127.0.0.1:8000`. La verificacion GET obtuvo el token desde `.env`
sin imprimirlo. El POST envio un evento de estado sin mensajes, evitando iniciar una
conversacion, llamar al LLM o enviar mensajes reales.

```text
GET /                         -> {"status":"ok"}
GET /webhook/whatsapp         -> 12345
POST /webhook/whatsapp        -> {"status":"ok"}
```
