# Verificacion de variantes de lenguaje para horarios

## Fecha

25 de septiembre de 2026.

## Cambio verificado

El detector determinista de disponibilidad reconoce `sacar cita`, incluida la
solicitud real `y para hoy quisiera sacar cita que tienes para hoy`. La solicitud
consulta los horarios mediante `check_availability` sin depender del LLM y conserva
el flujo normal cuando el paciente indica una hora exacta.

## Verificacion automatizada

- [x] Antes del cambio, el texto real no era detectado.
- [x] Despues del cambio, el texto real produce el rango de disponibilidad de hoy.
- [x] La prueba de disponibilidad paso con `4` pruebas.
- [x] La prueba de `ConversationService` paso con `18` pruebas.
- [x] La suite completa paso en la Raspberry Pi con `164` pruebas.

Comando ejecutado en el mirror:

```text
PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -m unittest discover -s /home/asaek/Downloads/chatbot_test_repo/tests -q
```

Resultado: `Ran 164 tests ... OK`.

## Verificacion operativa

La instancia sincronizada se reinicio en la Raspberry Pi sin enviar un mensaje real
a un paciente.

```text
GET /                         -> {"status":"ok"}
GET /webhook/whatsapp         -> 12345
POST /webhook/whatsapp        -> {"status":"ok"}
```
