# Verificacion del motivo antes de agendar

## Fecha

24 de septiembre de 2026.

## Alcance

Verificar que una solicitud de agendamiento pregunta el motivo antes de crear la
cita, conserva el horario entre mensajes y usa el motivo recibido para completar la
operacion.

## Verificacion automatizada

- [x] La reproduccion no crea la cita durante la primera solicitud.
- [x] El motivo recibido se guarda en la cita creada.
- [x] El estado pendiente sobrevive a la reconstruccion de `ConversationService`.
- [x] La suite completa paso en el mirror de Raspberry Pi con `158` pruebas.

Comando ejecutado en el mirror:

```text
PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -m unittest discover -s /home/asaek/Downloads/chatbot_test_repo/tests -v
```

Resultado: `Ran 158 tests ... OK`.

## Verificacion operativa

Se inicio temporalmente el checkout sincronizado en `127.0.0.1:18001`, con
`FakeCalendarProvider`, SQLite en `/tmp` y un token de prueba. No se invocaron
proveedores externos.

```text
GET /                         -> {"status":"ok"}
GET /webhook/whatsapp         -> 12345
POST /webhook/whatsapp        -> {"status":"ok"}
```

El POST uso un evento de estado no textual para comprobar el metodo sin iniciar una
respuesta LLM ni enviar un mensaje real por WhatsApp. La instancia temporal y sus
archivos fueron eliminados al terminar.
