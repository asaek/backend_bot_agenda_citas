# Diseno - Contrato de tool calling del LLM

## Estado

Implementado y verificado sin llamadas externas.

## Frontera

```text
ConversationService
    |
    v
LLMProvider.generate(messages)
    |
    v
LLMResponse = str | ToolCall
    |
    +-- texto -> WhatsAppClient
    |
    +-- ToolCall -> ejecutor futuro
```

`ToolCall` pertenece a la frontera del proveedor y contiene solo el nombre de la
operacion propuesta y sus argumentos no confiables. No contiene el alcance del
paciente. `ToolRequest` sigue siendo el tipo de dominio que el backend construira
despues de agregar `PatientScope`.

## Normalizacion

`OpenAICompatibleLLMProvider` envia en cada solicitud los cinco esquemas de
herramientas definidos por `tool_contracts.py` e inspecciona el primer mensaje de la primera
eleccion. Si existe `message.tool_calls`, acepta como maximo una entrada de tipo
`function`, decodifica `function.arguments` como JSON y devuelve `ToolCall`.

Tambien acepta `message.tool_call` cuando el adaptador o un fake ya entrega la
forma interna. En ambos casos el nombre debe ser texto no vacio y los argumentos
deben ser un objeto. La capa no conoce los argumentos requeridos de cada
herramienta; esa validacion pertenece a `parse_tool_request()`.

El proveedor usa `tool_choice=auto`. Si no hay tool call, el adaptador conserva el comportamiento textual existente:
recorta el contenido, rechaza respuestas vacias y aplica el limite configurado.

## Flujo actual

`ConversationService.build_reply()` propaga `LLMResponse`. El flujo de WhatsApp
envia un texto como antes. Si recibe `ToolCall` antes de que exista el ejecutor,
registra `UnsupportedToolCall` y envia la respuesta controlada. Esto evita
serializar una estructura interna en un mensaje para el paciente.

## Pruebas

Los tests usan `httpx.MockTransport` para respuestas textuales, tool calls nativos,
la forma normalizada y estructuras invalidas. `FakeLLMProvider` acepta cualquier
`LLMResponse`, lo que permite verificar el limite HTTP del webhook sin Internet.
