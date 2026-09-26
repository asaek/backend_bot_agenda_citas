# ADR 0027 - Señales de prioridad sin diagnostico

## Estado

Aceptada para el MVP tecnico.

## Contexto

Algunos mensajes del paciente pueden indicar que la solicitud merece una revision
prioritaria: perdida repentina de vision, dolor ocular, golpe o trauma, contacto con
sustancias quimicas, sangrado, destellos u otra alteracion visual importante. El
backend necesita conservar esa informacion para el doctor sin convertir el texto en
un diagnostico ni bloquear el flujo de creacion de citas.

## Decision

El evaluador mantiene una lista cerrada de codigos de señales de prioridad. Las
reglas locales detectan evidencia textual y el resultado del LLM solo puede conservar
codigos soportados y evidenciados por el texto del paciente. Cada codigo se convierte
en una descripcion operativa segura, por ejemplo:

> El paciente refiere alteracion visual que podria requerir atencion prioritaria.

Las descripciones no incluyen nombres de enfermedades como glaucoma o
desprendimiento, no contienen recomendaciones de tratamiento y no se presentan al
paciente como una conclusion clinica. El mismo catalogo se usa al componer la
notificacion interna al doctor. La señal se registra en la evaluacion del motivo y
puede acompañar la notificacion despues de una cita creada correctamente.

Una señal no cambia la autorizacion de la cita ni activa un triage automatico durante
este MVP. La validacion de calidad minima tambien rechaza referencias vagas como
`Lo de siempre`, porque no expresan un motivo util para la agenda.

## Consecuencias

- La prioridad queda separada de la categoria operativa y del motivo persistido.
- Un resultado del LLM no puede introducir diagnosticos como señales.
- Las notificaciones al doctor reciben lenguaje descriptivo y acotado.
- El flujo de agendamiento no cambia por detectar una señal.
- Antes de usar el sistema con pacientes reales se necesita una politica clinica
  explicita que defina umbrales, responsables, respuesta y seguimiento.
