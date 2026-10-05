# Verificacion del diagnostico de errores en modo debug

## Fecha

3 de octubre de 2026.

## Comportamiento

- `DEBUG_MODE` queda apagado por defecto en el ejemplo de configuracion.
- Con el modo activo, solo un remitente incluido en `DEBUG_WHATSAPP_NUMBERS` recibe el
  proveedor, tipo de error y codigo HTTP.
- Los demas remitentes conservan la respuesta generica.
- El diagnostico no incluye texto entrante, excepcion cruda, prompt, cuerpo HTTP ni
  credenciales.

## Verificacion automatizada en Raspberry Pi

Comando ejecutado:

```text
PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -m unittest discover -s /home/asaek/Downloads/chatbot_test_repo/tests -q
```

Resultado: `Ran 212 tests ... OK`.

Las pruebas del webhook verifican el diagnostico HTTP 429 al remitente autorizado, la
respuesta generica para un numero no autorizado y el modo apagado por defecto.

## Configuracion de depuracion

Se habilito `DEBUG_MODE` solo para el numero de prueba que inicio la solicitud de cambio;
el valor del numero no se copia a esta evidencia. Los dos valores de configuracion se
transfirieron selectivamente y el `.env` remoto conserva modo `600`.

La funcion produjo, sin llamar a Groq ni enviar un WhatsApp real:

```text
Diagnóstico debug: proveedor=groq; error=LLMHTTPError; HTTP=429.
```

## Runtime

Uvicorn se reinicio despues de verificar PID y listener; ngrok permanecio activo. Se
comprobaron localmente y mediante la URL publica:

```text
GET /                         -> 200 {"status":"ok"}
GET /webhook/whatsapp         -> 200 (challenge verificado)
POST /webhook/whatsapp        -> 200 {"status":"ok"} (evento de estado sin mensajes)
```
