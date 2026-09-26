# Verificacion de seleccion de horario controlada por el backend

## Fecha

26 de septiembre de 2026.

## Alcance

Verificar que la fecha y los slots ofrecidos se conservan en la conversacion, que la
seleccion de una hora no depende del LLM y que el transcript que repetia el motivo solo
crea una cita con el texto del paciente.

## Verificacion automatizada

- [x] La disponibilidad persiste `target_date`, slots, creacion y expiracion en
      `pending_appointment_availability`.
- [x] `damela a las 10 am` se valida contra los slots ofrecidos.
- [x] La seleccion valida usa las preguntas fijas del backend y no invoca al LLM.
- [x] El transcript `Hola quisiera agendar una cita para el lunes` -> `damela a las
      10 am` -> `Siento rara la vista` solicita el motivo una sola vez.
- [x] El flujo crea una sola cita a las 10:00 con `Siento rara la vista`.
- [x] La suite de disponibilidad paso con `6` pruebas.
- [x] La suite de `ConversationService` paso con `28` pruebas.
- [x] La suite completa paso en la Raspberry Pi con `198` pruebas.

## Comando ejecutado en el mirror

```text
PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -m unittest discover -s /home/asaek/Downloads/chatbot_test_repo/tests -q
```

Resultado: `Ran 198 tests ... OK`.

La ejecucion mostro una advertencia de deprecacion de Starlette sobre `httpx`; no
provoco fallos.
