# 0003 - Contrato de proveedor LLM y Groq como primera implementacion

## Estado

Aceptada para el primer incremento de la etapa 4.

## Contexto

El proyecto necesita generar respuestas mediante un LLM, pero debe poder
cambiar de proveedor sin mezclar detalles de HTTP y credenciales con la logica
conversacional. El MVP utiliza Groq para las primeras pruebas.

## Decision

Se define un protocolo asincrono `LLMProvider` cuyo metodo
`generate(messages)` devuelve texto. La primera implementacion es un adaptador
compatible con OpenAI, que usa `httpx` contra la API de Groq.

La configuracion se obtiene exclusivamente de variables de entorno. El cliente
HTTP se puede inyectar en pruebas para no depender de un servicio externo.

## Consecuencias

- La logica conversacional no queda atada a Groq.
- Se evita agregar un framework de agentes antes de necesitarlo.
- Groq es el proveedor inicial, pero el modelo y la URL se pueden cambiar por
  configuracion.
- El contrato no resuelve todavia la construccion del historial ni los reintentos.

## Alternativas descartadas por ahora

- Integrar directamente el SDK de un proveedor en `main.py`.
- Agregar LangChain u otro framework antes de implementar herramientas.
- Activar llamadas al LLM desde el webhook antes de contar con pruebas del
  adaptador.

## Actualizacion

El adaptador implementado se generalizo como `OpenAICompatibleLLMProvider`.
Groq continua siendo el proveedor predeterminado y OpenRouter puede utilizar el
mismo adaptador cambiando `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_API_KEY` y
`LLM_MODEL`. La decision de no agregar un framework de agentes se mantiene.

El tercer incremento inyecto el proveedor en `ConversationService`. El servicio
construye el contexto y solicita la respuesta; `main.py` coordina el envio por
WhatsApp y el registro de estados, manteniendo fuera de `main.py` la logica de
conversacion.
