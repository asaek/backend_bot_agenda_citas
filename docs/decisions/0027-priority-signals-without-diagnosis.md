# ADR 0027 - Señales de prioridad sin diagnostico

## Estado

Aceptada para el MVP tecnico. Ampliada el 7 de octubre de 2026 para analizar el
motivo y el historial de la gestion actual con evidencia literal.

## Contexto

Algunos mensajes del paciente pueden indicar que la solicitud merece una revision
prioritaria: perdida repentina de vision, dolor ocular, golpe o trauma, contacto con
sustancias quimicas, sangrado, destellos, ojos rojos, secrecion ocular amarillenta,
verdosa o abundante u otra alteracion visual importante. El
backend necesita conservar esa informacion para el doctor sin convertir el texto en
un diagnostico ni bloquear el flujo de creacion de citas.

## Decision

El evaluador mantiene una lista cerrada de codigos de señales de prioridad. Las
reglas locales detectan evidencia textual, incluyendo ojos rojos como `eye_redness`
y secrecion amarillenta, verdosa o abundante como `ocular_discharge`. La deteccion
tolera variantes como `laga;as` sin modificar el motivo persistido.

El LLM interpreta significado, sinonimos, errores de escritura, intensidad e inicio
de los sintomas. Su respuesta conserva `priority_signals` como lista de codigos y
agrega `priority_signal_evidence`, una lista de objetos `{signal, quote}`. El backend
exige un codigo soportado y una cita literal del paciente para conservar una
interpretacion semantica; no vuelve a exigir coincidencia con las expresiones
regulares. La evidencia se compara normalizando espacios, mayusculas y acentos,
y no se muestra en el cuerpo final. Una respuesta antigua sin evidencia conserva
solamente el respaldo local. Una lista de señales vacia no borra señales locales.

El evaluador previo a agendar usa el motivo. El compositor usa ese motivo y los
mensajes del paciente de la gestion actual, dentro del limite de historial configurado.
`DoctorNotificationRepository` identifica el evento anterior por la identidad estable
`appointment:<incoming_message_id>:...`, sin depender del estado de entrega. Tambien
se reconoce una respuesta fija de exito enviada por el backend como cierre de gestion.
Los mensajes posteriores al evento se excluyen. Los textos del asistente pueden
ayudar a resumir la conversacion, pero no sirven como evidencia de sintomas.

El formato final solo acepta codigos o descripciones exactas del catalogo; no hereda
señales de otras citas ni acepta estados de cita como señales.
Cada codigo se convierte en una descripcion operativa segura, por ejemplo:

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
- Los estados o confirmaciones de una cita no se pueden incluir como señales de prioridad.
- El historial actual puede aportar una señal aunque el motivo final no repita el sintoma.
- El modelo clasifica semanticamente; el backend comprueba catalogo y procedencia de
  evidencia, sin convertir las reglas locales en la unica interpretacion posible.
- Las negaciones explicitas se excluyen del respaldo local; una negacion posterior
  del mismo sintoma reemplaza su mencion anterior en la gestion actual. La ausencia
  de señales sigue siendo valida para revisiones rutinarias.
- El flujo de agendamiento no cambia por detectar una señal.
- Antes de usar el sistema con pacientes reales se necesita una politica clinica
  explicita que defina umbrales, responsables, respuesta y seguimiento.
