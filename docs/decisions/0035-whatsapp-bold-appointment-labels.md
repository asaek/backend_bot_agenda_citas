# ADR 0035 - Negrita compatible con WhatsApp en citas

## Estado

Aceptada.

## Contexto

WhatsApp no interpreta Markdown completo, pero reconoce marcadores sencillos de
formato en los mensajes de texto. Las etiquetas del bloque de citas se veian como
texto plano, por lo que el horario y el motivo tenian poca jerarquia visual.

## Decision

Aplicar negrita con un asterisco simple alrededor de las etiquetas `Horario:` y
`Motivo de consulta:`. Conservar el guion de la lista y el motivo como texto plano;
no usar HTML, tablas Markdown ni la sintaxis de doble asterisco de otros renderizadores.

```text
- *Horario:* HH:MM a HH:MM
  *Motivo de consulta:*
  <motivo de la cita>
```

## Consecuencias

- WhatsApp destaca las dos etiquetas sin cambiar el texto del motivo.
- El formato solo usa marcadores que WhatsApp admite en mensajes de texto; no depende
  de un renderizador Markdown completo.
- La regresion verifica los marcadores enviados en el prompt y una prueba con Groq
  comprueba la respuesta con datos sinteticos.
