# Diseno - Agente LLM basico

## Estado

Implementado y verificado para el agente LLM basico y su ciclo de pruebas sin
API.

## Componentes

```text
Conversation Service
    |
    v
Construccion del contexto
    |
    v
LLMProvider.generate(messages)
    |
    v
OpenAICompatibleLLMProvider
    |
    v
Proveedor API /chat/completions
    |
    v
Conversation Service -> WhatsAppClient -> WhatsApp
```

`LLMProvider` es un protocolo asincrono. Recibe una secuencia de `ChatMessage`
con `role` y `content`, y devuelve un `LLMResponse`: texto generado o un
`ToolCall` con nombre y argumentos. El consumidor no conoce la URL, los headers
ni el formato JSON del proveedor.

## Configuracion

`load_llm_settings()` convierte las variables de entorno en un objeto inmutable
`LLMSettings`. La funcion valida credenciales, modelo y limites positivos antes
de crear un proveedor.

La implementacion actual acepta `LLM_PROVIDER=groq` y
`LLM_PROVIDER=openrouter`. Ambos usan el mismo adaptador; se seleccionan el
endpoint, la API key y el modelo mediante variables de entorno. La salida se
limita a 4000 caracteres por defecto mediante `LLM_MAX_RESPONSE_CHARACTERS`.

## Transporte

`OpenAICompatibleLLMProvider` usa `httpx.AsyncClient` y el endpoint compatible
con OpenAI:

```text
{LLM_BASE_URL}/chat/completions
```

El cliente HTTP puede inyectarse. Esto evita llamadas reales durante las
pruebas y permite probar Groq y OpenRouter con el mismo codigo.

Las solicitudes usan `temperature=0` para reducir variaciones entre mensajes
equivalentes. Esto no sustituye la validacion del backend ni convierte al LLM en
fuente de verdad de la agenda.

## Pruebas sin API

`tests/fakes.py` contiene `FakeLLMProvider`, que cumple el contrato
`LLMProvider`, conserva cada secuencia de `ChatMessage` recibida y expone el
numero de llamadas mediante `call_count`. Su respuesta y su error son
configurables.

Las pruebas del webhook sustituyen las fabricas de dependencias de `main.py`,
usan `FakeWhatsAppClient` y una base SQLite temporal. Asi verifican el agente en
su frontera HTTP sin consumir una API ni enviar mensajes reales.

## Manejo de errores

Los errores de `httpx` se convierten en `LLMProviderError`. La respuesta JSON se
valida antes de acceder al contenido o a `tool_calls`, y una respuesta vacia,
con mas de una herramienta o con argumentos que no sean un objeto tambien se
rechaza.

## Construccion del contexto

`ConversationService.build_chat_messages(context)` llama a
`get_history(context.conversation_id)` despues de que el mensaje entrante ya fue
persistido. Anteponer un `ChatMessage` con el prompt de sistema y conservar los
mensajes persistidos en orden permite que el ultimo mensaje entrante quede como
el mensaje `user` actual sin duplicarlo.

El prompt se completa en cada solicitud con el reloj y la zona horaria del
`ToolExecutor`. Incluye la fecha y hora local, ademas de rangos ISO de inicio de
dia para hoy, manana y ayer. Asi el LLM puede convertir una expresion como
"hoy" a un rango de `list_appointments` sin pedir una fecha que el backend ya
conoce.

La conversion usa `user` para mensajes entrantes y `assistant` para respuestas
salientes con estado `sent`. Las respuestas `failed` no se incluyen porque no
fueron entregadas al paciente. El historial se recorta a los ultimos 30
mensajes por defecto, con un limite positivo configurable por llamada.

El prompt de sistema exige respuestas en español, breves y claras, sin inventar
datos, afirmar acciones externas, proporcionar diagnosticos medicos ni usar un
formato distinto de texto normal. Tambien distingue citas vigentes de estados
cancelados, completados o `no_show`.

## Ciclo integrado

`ConversationService` recibe un `LLMProvider` y el limite de historial mediante
inyeccion de dependencias. `build_reply(context)` construye el contexto y espera
`generate(messages)`. `main.py` crea las dependencias, llama al servicio y envia
respuestas de texto con `WhatsAppClient`. Si recibe un `ToolCall` antes de
integrar el ejecutor, registra el tipo `UnsupportedToolCall` y envia la respuesta
controlada; nunca serializa la llamada como texto para el paciente.

Si la generacion falla, `main.py` registra el tipo de error en la tabla de
fallos del LLM y envia la respuesta controlada. Si WhatsApp esta disponible, la
respuesta controlada se registra como `sent`; si tambien falla, queda como
`failed`. Como las respuestas fallidas no forman parte del contexto, el
siguiente webhook puede reintentar la generacion sin presentar una respuesta no
entregada al modelo.

Cuando la respuesta ya fue registrada como `sent`, `main.py` omite la
generacion y el envio para un webhook duplicado del mismo mensaje entrante.
