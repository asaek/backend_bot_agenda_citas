# ADR 0043 - Seleccion del proveedor OpenAI-compatible por entorno

## Estado

Aceptada.

## Contexto

El agente ya usaba `OpenAICompatibleLLMProvider` con Groq y OpenRouter. Se quiere
agregar la API de OpenAI y poder alternar entre Groq y OpenAI modificando solo el
selector de proveedor, sin cambiar el contrato conversacional ni introducir una
dependencia nueva.

## Decision

Se conserva el adaptador `httpx`; `LLM_PROVIDER` selecciona `groq`, `openai` u
`openrouter`, y cada uno usa su endpoint oficial. OpenAI usa Responses API;
Groq y OpenRouter usan Chat Completions. Cada proveedor obtiene su propia API
key, modelo y URL opcional desde variables con prefijo del proveedor. Las URLs
oficiales son los defaults. La API key y el modelo genericos existentes se
aceptan como fallback para el proveedor seleccionado; si hay variables
especificas, estas tienen precedencia. `LLM_BASE_URL` se mantiene como fallback
solo para Groq y OpenRouter.

Para OpenAI, `LLM_MAX_OUTPUT_TOKENS` se serializa como `max_output_tokens`;
Groq y OpenRouter conservan `max_tokens`. Responses tool calls conservan los
elementos originales de salida en memoria y los devuelven junto con
`function_call_output`, sin almacenar la respuesta remota (`store=false`). Los
tres proveedores continúan usando el mismo protocolo `LLMProvider` y los mismos
contratos de texto y llamadas a herramientas.

## Consecuencias

- Con las claves y modelos de ambos proveedores configurados, alternar entre
  Groq y OpenAI solo requiere cambiar `LLM_PROVIDER` y reiniciar el backend.
- Si se usa `LLM_API_KEY` y `LLM_MODEL` para un solo proveedor activo, ambos valores
  deben actualizarse al cambiar el selector.
- Las llamadas conversacionales, la evaluacion del motivo y los resumenes de
  notificaciones continúan usando la misma instancia de proveedor.
- No se agrega el SDK de OpenAI ni una nueva dependencia de ejecución.
- OpenAI puede usar `gpt-oss-20b`, cuyo ID oficial requiere Responses API; el
  prefijo `openai/` de configuraciones Groq no se reutiliza en OpenAI.
- Los IDs de modelo se envian sin reescritura y deben ser validos para el endpoint
  seleccionado.

## Verificacion

Las pruebas usan `httpx.MockTransport` para verificar ambos protocolos, la URL,
autenticacion, modelo, limite de tokens, tool calls y la reproduccion de elementos
de razonamiento de OpenAI sin credenciales ni llamadas reales.
