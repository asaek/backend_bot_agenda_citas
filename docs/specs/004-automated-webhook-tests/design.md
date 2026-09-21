# Diseno - Pruebas automatizadas del ciclo sin API

## Estado

Implementado y verificado.

## Limite de prueba

```text
TestClient
    |
    v
POST /webhook/whatsapp
    |
    +-- ConversationService -> SQLite temporal
    |
    +-- FakeLLMProvider -> registra ChatMessage y devuelve texto o ToolCall
    |
    +-- FakeWhatsAppClient -> registra destinatario y cuerpo
```

Las pruebas sustituyen las fabricas de dependencias de `main.py` dentro del
contexto de cada caso. El codigo de produccion sigue usando
`OpenAICompatibleLLMProvider`; el fake vive unicamente en `tests/fakes.py`.

## FakeLLMProvider

`FakeLLMProvider` implementa el metodo asincrono `generate(messages)` del
protocolo `LLMProvider`. Convierte la secuencia recibida en una lista y la
guarda en `received_messages`, por lo que las pruebas pueden inspeccionar el
prompt, el historial, el mensaje actual y el numero de llamadas mediante
`call_count`.

Su respuesta es configurable como texto o `ToolCall`. Tambien acepta un
`LLMProviderError` para cubrir el camino de fallo sin lanzar excepciones de red.

## Casos cubiertos

- `test_conversation_service.py` verifica la transformacion del historial y el
  orden de los roles.
- `test_main.py` verifica el mensaje actual, el envio, el estado `sent`, la
  idempotencia, los fallos del LLM y la verificacion de Meta.
- SQLite usa una ruta temporal por caso para evitar depender de la base local.
- `FakeWhatsAppClient` evita cualquier solicitud a Graph API.
