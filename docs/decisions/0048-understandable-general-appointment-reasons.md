# ADR 0048 - Motivos generales comprensibles y aclaraciones diferenciadas

## Estado

Aceptada. Sustituye la politica de degradacion indiferenciada de ADR 0026.

## Contexto y decision

Agendar requiere identificar la razon de la visita, no obtener detalle clinico.
`Tengo problemas en el ojo izquierdo` es un motivo suficiente. El prompt acepta
descripciones generales y el backend acepta una categoria oftalmologica reconocida
con confianza aun cuando el modelo solicite mas detalle. Las categorias operativas
`visual_symptom`, `follow_up`, `routine_exam` y `procedure` ya identifican esa razon;
`other`, `unknown` y `out_of_scope` no habilitan esta excepcion.

Un respaldo local positivo reconoce expresiones completas de molestias o problemas
oculares y revisiones generales; no usa coincidencias aisladas de `ojo` ni rechaza
otros motivos por no estar en ese respaldo. Si el evaluador falla o contradice una
de esas expresiones, la regla local permite continuar y registra `source=rules`,
`confidence=1.0` y `validation_code=understandable_general_reason`. Esta confianza
corresponde a la regla, no se presenta como confianza del modelo. El fallo tecnico
sigue registrado en `llm_failures`; el texto del paciente es el unico motivo guardado.

Cuando no hay respaldo local suficiente, un fallo de llamada o formato informa
del problema tecnico y conserva el horario, permitiendo reenviar el mismo texto.
Una confianza insuficiente expresa incertidumbre de la evaluacion; no afirma que
el paciente sea incomprensible ni que el motivo este fuera de alcance. Un motivo
que realmente no identifica la visita recibe una aclaracion que reconoce la
referencia o cita el texto legible recibido. `attempt_count` selecciona preguntas
progresivas: pregunta abierta, opciones concretas y ejemplos de una respuesta
general suficiente. El contador sigue contando evaluaciones, incluidos errores.

No se añade una regla del consultorio que exija sintomas especificos, diagnostico,
intensidad o duracion. Las señales de prioridad y la validacion normal de horario,
disponibilidad y alcance del paciente siguen aplicandose antes de crear la cita.
