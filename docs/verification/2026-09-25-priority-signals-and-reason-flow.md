# Verificacion de señales de prioridad y flujo del motivo

## Fecha

25 de septiembre de 2026.

## Alcance

Verificar que la prioridad se conserva como una señal operativa separada de un
diagnostico, que los motivos invalidos no crean citas ni notifican al doctor y que el
horario pendiente se conserva hasta recibir un motivo valido.

## Verificacion automatizada

- [x] `jnbajnbsdijkqnbwikbdqwd` y `asdf` no crean una cita.
- [x] `Veo borroso desde ayer` crea una cita.
- [x] `Me duele el ojo y está rojo` crea una cita y registra `eye_pain`.
- [x] `Revisión general` crea una cita.
- [x] `Lo de siempre` solicita aclaracion.
- [x] Un motivo valido despues de uno invalido crea una sola cita.
- [x] El horario de la 1 pm permanece conservado.
- [x] Un motivo invalido no emite evento ni notificacion al doctor.
- [x] Las señales de perdida visual, dolor, trauma, exposicion quimica, sangrado,
      destellos y alteracion visual importante usan codigos soportados.
- [x] Las descripciones de señales no contienen diagnosticos como glaucoma o
      desprendimiento.
- [x] La suite completa paso en el mirror de Raspberry Pi con `194` pruebas.

Comando ejecutado en el mirror:

```text
PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -m unittest discover -s /home/asaek/Downloads/chatbot_test_repo/tests -v
```

Resultado: `Ran 194 tests ... OK`.

## Verificacion operativa

Se inicio temporalmente el checkout sincronizado en `127.0.0.1:18004`, con
`FakeCalendarProvider`, SQLite temporal y un token de prueba. No se invocaron
proveedores externos ni se envio un mensaje real de WhatsApp.

```text
GET /                         -> {"status":"ok"}
GET /webhook/whatsapp         -> 12345
POST /webhook/whatsapp        -> {"status":"ok"}
```

El POST uso un evento sin mensajes de texto, por lo que no inicio una evaluacion LLM,
una respuesta al paciente ni una llamada a WhatsApp Cloud API.

## Limite clinico

La implementacion solo genera una señal interna y no realiza diagnostico, triage ni
instrucciones de emergencia. Antes de operar con pacientes reales debe aprobarse una
politica clinica explicita.
