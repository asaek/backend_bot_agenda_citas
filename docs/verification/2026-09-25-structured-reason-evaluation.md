# Verificacion de evaluacion estructurada del motivo

## Fecha

25 de septiembre de 2026.

## Alcance

Verificar que el motivo legible se evalua mediante JSON estructurado, que el backend
aplica la confianza minima, que las señales se filtran y que el estado conserva los
intentos y la ultima evaluacion entre reconstrucciones del servicio.

## Verificacion automatizada

- [x] Se parsean `quality`, `category`, `priority_signals` y `confidence`.
- [x] Un texto rechazado localmente no consume una llamada al LLM.
- [x] Una respuesta invalida o con confianza menor a `0.75` no autoriza la cita.
- [x] Las señales no soportadas o no evidenciadas en el texto se descartan.
- [x] Una señal compatible se registra aunque el LLM no la incluya.
- [x] `out_of_scope` conserva la solicitud pendiente.
- [x] Los intentos y la evaluacion sobreviven a la reconstruccion de
      `ConversationService`.
- [x] El motivo guardado es el texto normalizado del paciente, no el valor sugerido
      por el LLM.
- [x] La suite completa paso en el mirror de Raspberry Pi con `182` pruebas.

Comando ejecutado en el mirror:

```text
PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -m unittest discover -s /home/asaek/Downloads/chatbot_test_repo/tests -v
```

Resultado: `Ran 182 tests ... OK`.

## Verificacion operativa

Se inicio temporalmente el checkout sincronizado en `127.0.0.1:18003`, con
`FakeCalendarProvider`, SQLite temporal y un token de prueba. No se invocaron
proveedores externos ni se envio un mensaje real de WhatsApp.

```text
GET /                         -> {"status":"ok"}
GET /webhook/whatsapp         -> 12345
POST /webhook/whatsapp        -> {"status":"ok"}
```

El POST uso un evento sin mensajes de texto, por lo que no inicio una evaluacion LLM,
una respuesta al paciente ni una llamada a WhatsApp Cloud API.
