# Verificacion de horarios libres antes de agendar

## Fecha

24 de septiembre de 2026.

## Alcance

Verificar que una solicitud de cita con fecha pero sin hora consulta los espacios
libres, no crea una cita y espera la seleccion del paciente.

## Verificacion automatizada

- [x] `Agendame una cita para manana` devuelve los espacios de 30 minutos.
- [x] La solicitud no invoca al LLM ni crea una cita.
- [x] Los horarios duplicados entre calendarios se muestran una sola vez.
- [x] Una solicitud con hora exacta conserva el flujo normal.
- [x] La suite completa paso en el mirror de Raspberry Pi con `162` pruebas.

Comando ejecutado en el mirror:

```text
PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -m unittest discover -s /home/asaek/Downloads/chatbot_test_repo/tests -q
```

Resultado: `Ran 162 tests ... OK`.

## Verificacion operativa

La instancia sincronizada se reinicio temporalmente en `127.0.0.1:8000`.

```text
GET /                         -> {"status":"ok"}
GET /webhook/whatsapp         -> 12345
POST /webhook/whatsapp        -> {"status":"ok"}
```

El POST uso un evento de estado no textual y no envio un mensaje real por WhatsApp.
