# Verificacion del nombre del paciente antes de agendar

## Fecha

26 de septiembre de 2026.

## Alcance

Verificar que una persona sin nombre registrado recibe primero la solicitud de
nombre, que el valor se persiste, que un reintento del mismo mensaje no lo usa como
motivo y que un motivo posterior completa la cita.

## Verificacion automatizada

- [x] Un paciente sin nombre recibe la pregunta por su nombre antes del motivo.
- [x] El nombre normalizado se persiste en `patients.name`.
- [x] El reintento del mensaje que entrega el nombre solo repite la pregunta por el
      motivo.
- [x] El motivo posterior conserva el horario pendiente y crea una sola cita.
- [x] La notificacion al doctor usa el nombre persistido.
- [x] La suite completa paso en el mirror de Raspberry Pi con `195` pruebas.

Comando ejecutado en el mirror:

```text
PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -m unittest discover -s /home/asaek/Downloads/chatbot_test_repo/tests -v
```

Resultado: `Ran 195 tests ... OK`.

## Verificacion operativa

Se inicio temporalmente el checkout sincronizado en `127.0.0.1:18005`, con
`FakeCalendarProvider`, SQLite temporal y un token de prueba. No se invocaron
proveedores externos ni se enviaron mensajes reales de WhatsApp.

```text
GET /                         -> {"status":"ok"}
GET /webhook/whatsapp         -> 12345
POST /webhook/whatsapp        -> {"status":"ok"}
```

El POST uso un evento de estado no textual para comprobar el metodo sin iniciar una
respuesta LLM ni una llamada a WhatsApp Cloud API. La instancia temporal fue
detenida al terminar la prueba.
