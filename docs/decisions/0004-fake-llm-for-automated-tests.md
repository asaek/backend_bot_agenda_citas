# 0004 - Fake LLM para pruebas automatizadas

## Estado

Aceptada.

## Contexto

El webhook ahora coordina persistencia, generacion y envio. Probar ese ciclo con
un proveedor real consume cuota, depende de la red y puede enviar mensajes no
deseados durante una prueba automatica.

## Decision

Las pruebas usaran `FakeLLMProvider`, un doble local que cumple el protocolo
`LLMProvider`, registra las secuencias recibidas y permite devolver una respuesta
determinista o lanzar un `LLMProviderError` configurado.

El fake se mantendra dentro de `tests/` y no se seleccionara mediante variables
de entorno en la aplicacion. Las pruebas sustituiran las dependencias del
webhook y usaran un cliente falso de WhatsApp y una base SQLite temporal.

## Consecuencias

- El flujo completo puede verificarse sin API key, Internet ni mensajes reales.
- Las pruebas observan tanto el contexto enviado al LLM como sus efectos en
  WhatsApp y SQLite.
- La aplicacion conserva el adaptador real sin agregar una dependencia de
  pruebas al runtime.
- El fake no demuestra la calidad ni la disponibilidad de un modelo real.

## Alternativas descartadas por ahora

- Usar un modelo real en las pruebas del webhook.
- Agregar un modo `LLM_PROVIDER=fake` al entorno de produccion.
- Mockear metodos internos del `ConversationService` en lugar de probar su
  frontera `LLMProvider`.
