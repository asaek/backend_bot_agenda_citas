# Verificacion de continuacion de fecha y diagnostico LLM

## Fecha

29 de septiembre de 2026.

## Cambio verificado

- Una intencion reconocible de agendar sin fecha guarda `pending_appointment_date`
  durante 10 minutos y pregunta el dia desde el backend; la prueba recrea el servicio
  entre turnos para comprobar que el estado se recupera de SQLite.
- Una respuesta posterior como `hoy` consulta `check_availability` usando la zona
  horaria de agenda y no invoca al LLM.
- `LLMHTTPError` conserva su codigo numerico en `llm_failures.http_status_code` y en
  un log operativo que no incluye el texto entrante.
- La inicializacion agrega la columna nullable a una base previa y conserva sus filas.

## Verificacion automatizada en Raspberry Pi

Comando ejecutado en el mirror:

```text
PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -m unittest discover -s /home/asaek/Downloads/chatbot_test_repo/tests -q
```

Resultado: `Ran 201 tests ... OK`.

La prueba del webhook usa `LLMHTTPError(429)` simulado y verifica el codigo persistido.
La prueba de migracion parte de una tabla `llm_failures` antigua. No se consulta un LLM
real ni se envia un mensaje real de WhatsApp.

## Verificacion HTTP aislada

Se ejecuto temporalmente Uvicorn en `127.0.0.1:18765` con una base SQLite temporal y un
Verify Token de prueba:

```text
GET /                         -> 200 {"status":"ok"}
GET /webhook/whatsapp         -> 200 12345
POST /webhook/whatsapp        -> 200 {"status":"ok"} (evento sin mensaje de texto)
```

## Limitacion de los registros anteriores

Los fallos del 29 de septiembre se conservaban solo como `LLMResponseError` y
`LLMHTTPError`; el codigo HTTP de esos fallos no puede recuperarse retrospectivamente.
Los nuevos fallos HTTP conservaran ese dato para el siguiente diagnostico.
