# 0003 - Contrato de proveedor LLM y Groq como primera implementacion

## Estado

Aceptada para el primer incremento de la etapa 4.

## Contexto

El proyecto necesita generar respuestas mediante un LLM, pero debe poder
cambiar de proveedor sin mezclar detalles de HTTP y credenciales con la logica
conversacional. El MVP utiliza Groq para las primeras pruebas.

## Decision

Se define un protocolo asincrono `LLMProvider` cuyo metodo
`generate(messages)` devuelve texto. La primera implementacion es
`GroqLLMProvider`, que usa `httpx` contra la API compatible con OpenAI.

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
