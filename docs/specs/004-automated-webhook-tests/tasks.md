# Tareas - Pruebas automatizadas del ciclo sin API

## SDD

- [x] Definir el alcance y los criterios de aceptacion.
- [x] Documentar el limite de prueba y el proveedor falso.
- [x] Registrar la decision de no consumir servicios externos en la suite.

## Implementacion

- [x] Crear `tests/fakes.py` con `FakeLLMProvider`.
- [x] Registrar mensajes recibidos y cantidad de llamadas.
- [x] Permitir respuestas exitosas y errores LLM simulados.
- [x] Reutilizar el fake en las pruebas del servicio y del webhook.

## Verificacion

- [x] Verificar la transformacion del historial y el mensaje actual.
- [x] Verificar envio por WhatsApp y persistencia como `sent`.
- [x] Verificar que un webhook duplicado no llama de nuevo al LLM.
- [x] Verificar el registro de errores del LLM.
- [x] Verificar la respuesta al challenge de Meta.
- [x] Ejecutar la suite sin credenciales ni Internet.
