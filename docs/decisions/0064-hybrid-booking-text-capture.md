# ADR 0064 - Captura hibrida de datos de reserva por texto

## Estado

Aceptada. Amplia ADR 0063 para mensajes complejos; mantiene la procedencia literal,
la validacion del nombre y la evaluacion independiente del motivo.

## Contexto y decision

La nueva conversacion del 28/10/2026 mostro que `motivo de la cita` no se reconocia
como separador. Los patrones de ADR 0063 tampoco cubrian explicaciones sin etiqueta
ni saludos junto con datos. Seguir ampliando exclusivamente las expresiones locales
dejaria al paciente condicionado a una redaccion particular.

`BookingTextInterpreter` conserva una ruta local para nombres y separadores claros
(consulta, cita o visita). Cuando detecta un nombre mezclado con una oracion o una
presentacion no resuelta, solicita al proveedor LLM existente un JSON con `intent`,
`patient_name`, `reason` y `confidence`. Esta extraccion no recibe herramientas ni
datos de otros turnos: solo el mensaje y el campo esperado.

Los campos deben ser fragmentos continuos literales del mensaje, normalizando
solo espacios, no superpuestos y con confianza minima `0.85`. Se rechazan campos
inventados, esquemas malformados y cortes que omiten un `no` o `sin` inmediato.
El prompt exige conservar el nombre completo y toda la explicacion del motivo,
incluidas duracion, negaciones y estudios. La validacion del nombre sigue pudiendo
solicitar confirmar un apellido inusual; la extraccion no lo acepta automaticamente.

El mismo resultado de interpretacion sirve al enrutamiento y a la captura, para
que un saludo o una pregunta de cortesia junto con datos no pause el flujo. Los
abandonos, cambios de gestion y cancelaciones explicitos conservan prioridad. Las
preguntas informativas identificadas como `other` siguen pausando la gestion.
La recuperacion de respuestas anteriores de ADR 0063 usa el mismo interprete.

## Consecuencias

- Los casos claros no agregan llamadas al LLM; los complejos pueden requerir una
  llamada de extraccion adicional antes de la evaluacion del motivo.
- El respaldo semantico admite mensajes de hasta 4000 caracteres; sin proveedor
  utilizable o con baja confianza se pide aclaracion sin reemplazar datos previos.
- Un fallo del proveedor o del esquema se registra como tecnico y permite reenviar
  el mismo mensaje, conservando el horario y los datos aceptados.
- No se añaden dependencias, servicios externos adicionales, migraciones ni
  confirmaciones de reserva; la ejecucion y entrega idempotente siguen en el backend.
