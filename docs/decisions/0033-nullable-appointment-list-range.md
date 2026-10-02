# ADR 0033 - Valores nulos para el rango opcional de citas

## Estado

Aceptada.

## Contexto

El esquema OpenAI-compatible permitia omitir `start_at` y `end_at` en
`list_appointments`, pero definia ambos campos como cadenas exclusivamente. Al
consultar todas las citas, Groq `openai/gpt-oss-20b` devolvio ambos argumentos con
valor `null`; Groq rechazo la llamada generada con HTTP 400 antes de que el backend
pudiera ejecutarla. El parser de agenda ya acepta `null` como ausencia de fecha.

## Decision

Declarar cada extremo del rango de `list_appointments` como `string` o `null` en el
esquema enviado al proveedor. La ausencia de ambos campos y el valor `null` en ambos
representan la misma consulta sin rango. El contrato de dominio sigue rechazando un
rango parcial.

## Consecuencias

- Groq puede entregar la llamada sin rango que genera para consultas como «qué citas
  tengo» sin que su validador de herramientas la rechace.
- La normalizacion permanece en `parse_tool_request`; no cambia el alcance del
  paciente ni la semantica de las consultas con rango.
- Las pruebas cubren tanto los argumentos nulos como el esquema que se publica al
  proveedor.

## Verificacion

El contexto de la consulta reportada fallo con el esquema anterior y devolvio HTTP
200 con `list_appointments` al permitir los valores nulos. La regresion automatizada
se ejecuto antes y despues del cambio en Raspberry Pi.
