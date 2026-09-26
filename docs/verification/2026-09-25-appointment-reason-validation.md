# Verificacion de validacion minima del motivo

## Fecha

25 de septiembre de 2026.

## Alcance

Verificar que un motivo evidentemente ilegible no crea una cita ni una notificacion,
que la solicitud pendiente conserva el horario y que un motivo valido posterior puede
completar la cita.

## Verificacion automatizada

- [x] El validador normaliza espacios sin reescribir el texto del paciente.
- [x] El validador rechaza texto vacio, simbolos, texto demasiado corto y ruido
      evidente.
- [x] `jnbajnbsdijkqnbwikbdqwd` no crea una cita.
- [x] La solicitud pendiente conserva el horario despues del rechazo.
- [x] Un motivo valido posterior crea la cita una sola vez.
- [x] No se emite un evento de cita mientras el motivo es rechazado.
- [x] La suite completa paso en el mirror de Raspberry Pi con `174` pruebas.

Comando ejecutado en el mirror:

```text
PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -m unittest discover -s /home/asaek/Downloads/chatbot_test_repo/tests -v
```

Resultado: `Ran 174 tests ... OK`.

## Verificacion operativa

Se inicio temporalmente el checkout sincronizado en `127.0.0.1:18002`, con
`FakeCalendarProvider`, SQLite temporal y un token de prueba. No se invocaron
proveedores externos ni se envio un mensaje real de WhatsApp.

```text
GET /                         -> {"status":"ok"}
GET /webhook/whatsapp         -> 12345
POST /webhook/whatsapp        -> {"status":"ok"}
```

El POST uso un evento sin mensajes de texto, por lo que no inicio una respuesta LLM
ni una llamada a WhatsApp Cloud API.
