# Verificacion de confirmaciones naturales de citas

## Objetivo

Comprobar que las respuestas afirmativas y negativas claras aceptan palabras de
cortesia, y que las respuestas contradictorias o inciertas siguen sin autorizar una
mutacion.

## Verificacion automatizada en Raspberry Pi

El clasificador reconoce `Si, por favor`, `Claro, adelante`, `Por supuesto, gracias`,
`De acuerdo, muchas gracias` y `No, gracias`. Las respuestas `Si, pero mejor no`,
`No estoy seguro, creo que si` y `Tal vez` permanecen ambiguas.

El flujo de reprogramacion de `ConversationService` se verifico con el mensaje
`Si, por favor`; la cita se modifica una sola vez. La suite completa paso con 210
pruebas:

```sh
PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo \
  /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python \
  -m unittest discover \
  -s /home/asaek/Downloads/chatbot_test_repo/tests -v
```
