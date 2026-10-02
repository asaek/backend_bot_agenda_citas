# ADR 0034 - Bloques para presentar citas en WhatsApp

## Estado

Aceptada.

## Contexto

La regla anterior pedia una cita por linea con hora y motivo. En las respuestas de
WhatsApp ambos datos aparecieron combinados, por ejemplo `10:00 a 10:30: ojos
rojos`, lo que dificulto leer claramente el motivo de consulta.

## Decision

Instruir al LLM para presentar cada cita en un bloque de varias lineas:

```text
- Horario: HH:MM a HH:MM
  Motivo de consulta:
  <motivo de la cita>
```

El horario y el motivo no se combinan en una linea, el texto del motivo se conserva
y se incluye la fecha cuando el resultado abarca mas de un dia. Se mantienen las
reglas existentes de no usar tablas Markdown ni exponer IDs internos.

## Consecuencias

- El paciente distingue el intervalo horario de la descripcion del motivo.
- El LLM conserva la responsabilidad de redactar la respuesta final; el prompt
  define ahora el formato concreto en vez de una lista generica.
- La prueba del prompt protege el formato de WhatsApp frente a cambios posteriores.
