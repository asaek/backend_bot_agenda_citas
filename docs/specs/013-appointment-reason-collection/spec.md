# 013 - Motivo antes de crear una cita

## Estado

Verificado. El backend solicita el nombre del paciente en cada cita nueva, aunque ya
este registrado, y solicita el motivo antes de crearla. Valida una calidad minima de
legibilidad, evalua el texto con una respuesta estructurada y conserva la solicitud
pendiente entre mensajes.
La evidencia esta en `docs/verification/2026-09-24-appointment-reason.md` y
`docs/verification/2026-09-25-appointment-reason-validation.md`, además de
`docs/verification/2026-09-25-structured-reason-evaluation.md` y
`docs/verification/2026-09-25-priority-signals-and-reason-flow.md`, además de
`docs/verification/2026-09-26-patient-name-before-booking.md`.
La recoleccion del nombre en cada cita esta verificada en
`docs/verification/2026-10-01-patient-name-every-booking.md`.

## Objetivo

Evitar que una cita se cree con un motivo inventado, predeterminado o completado por
el LLM cuando el paciente de prueba todavia no ha explicado la razon de su visita.

## Alcance

La funcionalidad cubre:

- Solicitud del motivo antes de ejecutar `create_appointment`.
- Solicitud y actualizacion del nombre del paciente antes de solicitar el motivo en
  cada cita nueva.
- Conservacion del horario solicitado mientras se espera el siguiente mensaje.
- Uso del texto del paciente como motivo de la cita.
- Validacion local de calidad minima antes de usar el texto como motivo.
- Rechazo de entradas evidentemente ilegibles sin perder el horario pendiente.
- Evaluacion estructurada opcional con `quality`, `category`, `priority_signals` y
  `confidence` validados por el backend.
- Señales de prioridad expresadas con descripciones operativas sin diagnosticos.
- Solicitud de aclaracion para referencias vagas como `Lo de siempre`.
- Persistencia de intentos, resultado, categoria, señales y fecha de evaluacion.
- Persistencia del estado pendiente en `conversations.context_json`.
- Expiracion de la solicitud pendiente despues de 10 minutos.
- Eventos y notificaciones solamente despues de crear la cita correctamente.

La creacion no requiere una confirmacion adicional de Si o No despues de recibir el
motivo.

## Requisitos funcionales

### RF-1301 - Motivo previo

Una solicitud de `create_appointment` no debe modificar el proveedor de calendario
hasta que el paciente de prueba haya enviado un motivo en un mensaje posterior.
El valor `reason` propuesto por el LLM no cuenta como motivo proporcionado por el
paciente.

### RF-1302 - Horario pendiente

La pregunta por el motivo debe conservar el horario solicitado y usarlo al ejecutar
la cita posteriormente. El paciente no debe tener que repetirlo.

### RF-1303 - Texto del paciente

El motivo persistido debe derivarse del mensaje del paciente que responde la pregunta.
El backend puede normalizar espacios, pero no debe sustituirlo por una categoria o
texto predeterminado. El mensaje debe superar la validacion de calidad minima antes
de ejecutar la cita.

### RF-1311 - Nombre del paciente

En cada solicitud nueva de cita, incluso si `patients.name` ya contiene un nombre,
el backend debe solicitar el nombre completo antes del motivo. El nombre normalizado
debe guardarse o actualizarse en el registro del paciente y la solicitud pendiente
debe conservarse hasta recibir ambos datos. Un nombre no textual, vacio o fuera del
limite permitido debe pedir una aclaracion y no debe crear la cita.

### RF-1312 - Reintento de entrega del nombre

Si se reintenta el mismo mensaje que entrego el nombre, el backend debe devolver la
pregunta por el motivo sin volver a tratar ese texto como motivo ni crear una cita.

### RF-1307 - Motivo evidentemente ilegible

Si el mensaje posterior esta vacio, no contiene letras, es demasiado corto o parece
texto evidentemente ilegible, el backend no debe crear la cita ni emitir una
notificacion. Debe conservar la solicitud pendiente y pedir al paciente que describa
el motivo con sus propias palabras.

### RF-1308 - Evaluacion estructurada

Cuando el texto supera las reglas locales, el evaluador puede solicitar al LLM una
respuesta JSON con `quality`, `category`, `priority_signals` y `confidence`. El
backend solo acepta `valid` con una categoria soportada distinta de `unknown` o
`out_of_scope` y una confianza minima de `0.75`. Una respuesta invalida, ausente o
con baja confianza se trata como `needs_clarification`.

El LLM no puede devolver el motivo de la cita, diagnosticar ni crear la cita. Las
señales se limitan a una lista de codigos soportados y solo se conservan cuando el
texto del paciente contiene evidencia compatible. Una señal de prioridad no bloquea
la cita durante este MVP, pero se registra en el contexto de la conversacion.

### RF-1309 - Estado de evaluacion

Mientras la solicitud este pendiente, el backend conserva el numero de intentos y la
ultima evaluacion con su resultado, categoria, señales, confianza y fecha. Cuando la
cita se completa, conserva esa evaluacion bajo `last_appointment_reason_evaluation`
y elimina solamente el estado pendiente.

### RF-1310 - Señal de prioridad sin diagnostico

Para mensajes que refieran perdida repentina de vision, dolor ocular, golpe o trauma,
contacto con sustancias quimicas, sangrado, destellos u otra alteracion visual
importante, el backend debe conservar una señal de prioridad operativa. La señal debe
usar un codigo soportado y una descripcion como `El paciente refiere una alteracion
visual que podria requerir atencion prioritaria.`; no debe nombrar glaucoma,
desprendimiento ni otra enfermedad.

La señal puede incluirse en la notificacion interna al doctor despues de crear la cita,
pero no cambia el flujo ni activa triage automatico. Antes de usarla con pacientes
reales debe existir una politica clinica explicita.

### RF-1304 - Persistencia

Si el proceso se reinicia despues de preguntar el motivo, el siguiente mensaje debe
continuar la misma solicitud pendiente.

### RF-1305 - Expiracion

Una solicitud pendiente con mas de 10 minutos debe descartarse sin crear una cita y
debe pedir al paciente que solicite nuevamente el horario.

### RF-1306 - Notificacion posterior

La primera pregunta no debe producir un evento de cita ni una notificacion al doctor.
Una notificacion solo puede emitirse despues de una creacion exitosa.

## Criterios de aceptacion

1. `Agendame otra cita a las 15:00` responde preguntando el motivo y no crea una
   cita.
2. `Revision de cornea` despues de la pregunta crea la cita a las 15:00 con ese
   motivo.
3. El flujo continua despues de reconstruir `ConversationService`.
4. El motivo sugerido por el LLM no se persiste si el paciente todavia no lo ha
   enviado.
5. Un texto evidentemente ilegible no crea una cita y permite continuar con un motivo
   valido posterior usando el horario original.
6. Una solicitud fallida o vencida no produce una notificacion de exito.
7. La respuesta final no muestra IDs internos de la agenda.
8. Una respuesta estructurada con baja confianza o categoria fuera de alcance pide
   aclaracion y no crea la cita.
9. Un motivo aceptado conserva el texto normalizado del paciente, registra los
   intentos y la evaluacion, y no usa texto producido por el LLM como `reason`.
10. `jnbajnbsdijkqnbwikbdqwd` y `asdf` no crean una cita ni generan una notificacion.
11. `Veo borroso desde ayer` y `Revisión general` crean una cita; un motivo valido
    posterior a uno invalido crea una sola cita y conserva el horario de la 1 pm.
12. `Me duele el ojo y está rojo` crea la cita y registra una señal de prioridad.
13. `Lo de siempre` conserva la solicitud pendiente y pide una aclaracion.
14. Una señal de prioridad y su notificacion no contienen diagnosticos ni cambian la
    respuesta de agendamiento.
15. Cada nueva cita pregunta primero el nombre, incluso si ya esta registrado; despues
    de recibirlo pregunta el motivo.
16. El nombre recibido reemplaza el valor de `patients.name`, el mismo mensaje
    reintentado no crea una cita y un motivo posterior crea la cita con el horario
    original.

## Fuera del alcance

- Clasificacion clinica o diagnostico del motivo.
- Validacion medica del texto del paciente.
- Triage clinico automatico o instrucciones de emergencia.
- Politica clinica para operar señales de prioridad con pacientes reales.
- Confirmacion interactiva adicional para crear la cita.
- Botones o plantillas especiales de WhatsApp.
