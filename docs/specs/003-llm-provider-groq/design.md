# Diseno - Contrato LLM y proveedor Groq

## Estado

Implementado y verificado para los dos primeros incrementos de la etapa 4.

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
GroqLLMProvider
    |
    v
Groq API /chat/completions
```

`LLMProvider` es un protocolo asincrono. Recibe una secuencia de `ChatMessage`
con `role` y `content`, y devuelve solamente el texto generado. El consumidor no
conoce la URL, los headers ni el formato JSON del proveedor.

## Configuracion

`load_llm_settings()` convierte las variables de entorno en un objeto inmutable
`LLMSettings`. La funcion valida credenciales, modelo y limites positivos antes
de crear un proveedor.

La implementacion actual acepta unicamente `LLM_PROVIDER=groq`. El resto del
sistema puede incorporar otro proveedor implementando el mismo protocolo sin
cambiar el contrato.

## Transporte

`GroqLLMProvider` usa `httpx.AsyncClient` y el endpoint compatible con OpenAI:

```text
{LLM_BASE_URL}/chat/completions
```

El cliente HTTP puede inyectarse. Esto evita llamadas reales durante las
pruebas y mantiene el mismo codigo de produccion para el siguiente incremento.

## Manejo de errores

Los errores de `httpx` se convierten en `LLMProviderError`. La respuesta JSON se
valida antes de acceder a `choices[0].message.content`, y una respuesta vacia o
con una estructura inesperada tambien se rechaza.

## Construccion del contexto

`ConversationService.build_chat_messages(context)` llama a
`get_history(context.conversation_id)` despues de que el mensaje entrante ya fue
persistido. Anteponer un `ChatMessage` con el prompt de sistema y conservar los
mensajes persistidos en orden permite que el ultimo mensaje entrante quede como
el mensaje `user` actual sin duplicarlo.

La conversion usa `user` para mensajes entrantes y `assistant` para respuestas
salientes con estado `sent`. Las respuestas `failed` no se incluyen porque no
fueron entregadas al paciente. El historial se recorta a los ultimos 30
mensajes por defecto, con un limite positivo configurable por llamada.

El prompt de sistema exige respuestas en español, breves y claras, sin inventar
datos, afirmar acciones externas, proporcionar diagnosticos medicos ni usar un
formato distinto de texto normal.

## Decision de alcance

El proveedor todavia no se inyecta en `ConversationService` y el webhook no se
modifica en este incremento. La respuesta fija se conserva hasta completar el
ciclo de generacion, registro de fallos y envio por WhatsApp.
