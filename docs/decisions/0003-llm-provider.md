# 0003 - Contrato de proveedor LLM

## Estado

Aceptada para el agente LLM basico de la etapa 4.

## Contexto

El agente basico necesita generar respuestas mediante un LLM, pero debe poder
cambiar de proveedor sin mezclar detalles de HTTP y credenciales con la logica
conversacional. El MVP utiliza Groq para las primeras pruebas y debe poder
verificarse sin consumir una API real.

## Decision

Se define un protocolo asincrono `LLMProvider` cuyo metodo
`generate(messages)` devuelve texto. La primera implementacion es
`OpenAICompatibleLLMProvider`, un adaptador que usa `httpx` contra la API de
Groq. OpenRouter utiliza el mismo adaptador mediante configuracion.

La configuracion se obtiene exclusivamente de variables de entorno. El cliente
HTTP se puede inyectar en pruebas para no depender de un servicio externo.
El ciclo completo usa un `FakeLLMProvider` en pruebas automaticas; el fake no es
una opcion de configuracion del entorno de produccion.

## Consecuencias

- La logica conversacional no queda atada a Groq.
- Se evita agregar un framework de agentes antes de necesitarlo.
- Groq es el proveedor inicial, pero el modelo y la URL se pueden cambiar por
  configuracion.
- La logica de herramientas y memoria avanzada queda fuera de este agente basico.

## Alternativas descartadas por ahora

- Integrar directamente el SDK de un proveedor en `main.py`.
- Agregar LangChain u otro framework antes de implementar herramientas.
- Seleccionar un proveedor concreto desde `main.py` y mezclar alli la logica
  conversacional.

## Actualizacion

El adaptador implementado se generalizo como `OpenAICompatibleLLMProvider`.
Groq continua siendo el proveedor predeterminado y OpenRouter puede utilizar el
mismo adaptador cambiando `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_API_KEY` y
`LLM_MODEL`. La decision de no agregar un framework de agentes se mantiene.

El agente basico inyecto el proveedor en `ConversationService`. El servicio
construye el contexto y solicita la respuesta; `main.py` coordina el envio por
WhatsApp y el registro de estados, manteniendo fuera de `main.py` la logica de
conversacion. La suite automatizada verifica este ciclo con dobles locales.
