# Verificacion de consulta de citas con rango nulo

## Fecha

1 de octubre de 2026.

## Diagnostico

Las consultas «Me podrias decir que citas tengo» quedaron registradas como
`LLMHTTPError` HTTP 400. Al reproducir el contexto de la segunda consulta contra
Groq, el proveedor informo que `list_appointments` recibio `start_at: null` y
`end_at: null`, mientras que el esquema publicado aceptaba solamente cadenas. El
error ocurria antes de ejecutar el `ToolExecutor` o consultar el calendario.

La prueba A/B del mismo contexto devolvio HTTP 400 con el esquema anterior y HTTP
200 solicitando `list_appointments` al declarar ambos argumentos opcionales como
`string` o `null`. La misma reproduccion con el esquema implementado tambien
devolvio HTTP 200 y solicito `list_appointments`.

## Cambio verificado

- [x] El esquema de `list_appointments` acepta `null` para `start_at` y `end_at`.
- [x] `parse_tool_request` trata ambos valores nulos como un rango omitido.
- [x] Un solo extremo nulo sigue rechazandose por el contrato de agenda.

## Verificacion automatizada en Raspberry Pi

La regresion del esquema fallo antes del cambio con:

```text
AssertionError: 'string' != ['string', 'null']
```

Despues del cambio, el archivo de contratos paso con 8 pruebas y la suite completa
paso con 205 pruebas:

```text
PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -m unittest discover -s /home/asaek/Downloads/chatbot_test_repo/tests -v
Ran 205 tests ... OK
```

## Error HTTP 429

La consulta anterior tambien acumulo errores HTTP 429, independientes del esquema
de herramientas. El cambio corrige el HTTP 400 reproducido; un 429 indica que el
proveedor limito temporalmente la solicitud y puede requerir disponibilidad o cuota
del proveedor.

## Runtime

Despues de sincronizar los cambios, se inspecciono el listener y se recargo
unicamente el PID Uvicorn verificado desde el directorio del proyecto. El tunel
ngrok existente continuo activo. Se comprobaron las rutas localmente y mediante
la URL publica; el POST uso un evento de estado sin mensajes, por lo que no llamo
al LLM ni envio mensajes de WhatsApp.

```text
GET /                         -> OK local y publico
GET /webhook/whatsapp         -> OK local y publico
POST /webhook/whatsapp        -> OK local y publico
```
