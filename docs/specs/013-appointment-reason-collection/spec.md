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
La señal `eye_redness` y el filtrado de señales libres del resumen se verificaron en
`docs/verification/2026-10-05-red-eye-priority-signals.md`.
Los abandonos y cambios de intencion mientras se espera el nombre o motivo se definen en
`specs/016-conversation-intent-routing/`.
La aclaracion conservadora del nombre esta verificada en Raspberry Pi en
`docs/verification/2026-10-08-patient-name-clarification.md`.
La aceptacion de motivos generales y las aclaraciones diferenciadas estan verificadas
en `docs/verification/2026-10-09-general-appointment-reasons.md`.

## Objetivo

Evitar que una cita se cree con un motivo inventado, predeterminado o completado por
el LLM cuando el paciente de prueba todavia no ha explicado la razon de su visita.

## Alcance

La funcionalidad cubre:

- Solicitud del motivo antes de ejecutar `create_appointment`.
- Solicitud y actualizacion del nombre del paciente antes de solicitar el motivo en
  cada cita nueva.
- Aclaracion de partes sospechosas del nombre, conservando el texto completo y el
  horario hasta recibir confirmacion o un nombre completo corregido.
- Conservacion del horario solicitado mientras se espera el siguiente mensaje.
- Uso del texto del paciente como motivo de la cita.
- Validacion local de calidad minima antes de usar el texto como motivo.
- Rechazo de entradas evidentemente ilegibles sin perder el horario pendiente.
- Evaluacion estructurada opcional con `quality`, `category`, `priority_signals` y
  `confidence` validados por el backend.
- Señales de prioridad expresadas con descripciones operativas sin diagnosticos.
- Deteccion de ojos rojos como señal de prioridad e inclusion en notificaciones al doctor.
- Solicitud de aclaracion para referencias vagas como `Lo de siempre`.
- Persistencia de intentos, resultado, categoria, señales y fecha de evaluacion.
- Aceptacion de motivos oftalmologicos generales comprensibles sin exigir detalle clinico.
- Respuestas distintas para motivo insuficiente, baja confianza y fallo tecnico.
- Aclaraciones progresivas que reconocen la referencia o el texto recibido.
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
La normalizacion solo ajusta espacios; no corrige letras, acentos, mayusculas ni
elimina partes. La respuesta de aceptacion muestra el nombre completo guardado.

### RF-1313 - Parte sospechosa del nombre

Si una palabra del nombre contiene señales claras de texto de prueba, el backend
debe mantener la captura del nombre activa y citar todo el nombre recibido al pedir
aclaracion, por ejemplo: `¿Me confirmas tus apellidos? Recibí ‘Asael Ponce jhbashkda’.`
La pregunta explica como confirmar la escritura o enviar el nombre completo corregido.
No guarda un nombre parcial ni reemplaza `patients.name` antes de aceptar la respuesta.

La sospecha no demuestra que un apellido sea falso. No se exige aparecer en un
diccionario y no se aplican reglas de vocales latinas a otros alfabetos. El paciente
puede confirmar explicitamente el candidato completo. Repetir un nombre sospechoso,
incluso con otro mensaje, vuelve a pedir aclaracion; una negativa solicita el nombre
completo corregido sin abandonar la reserva. Una respuesta invalida conserva el
candidato. Un segundo nombre sospechoso se evalua como nombre, no como motivo.
La aclaracion sobrevive un reinicio y una pausa; un `Si` mientras esta pausada no
acepta el nombre hasta retomar la gestion.

### RF-1312 - Reintento de entrega del nombre

Si se reintenta el mismo mensaje que entrego el nombre, el backend debe devolver la
pregunta por el motivo sin volver a tratar ese texto como motivo ni crear una cita.
Los reintentos de mensajes anteriores de aclaracion tampoco se convierten en motivo
ni reemplazan el candidato mas reciente. El mensaje que confirma un candidato
cuenta como entrega del nombre y conserva la misma proteccion.

### RF-1307 - Motivo evidentemente ilegible

Si el mensaje posterior esta vacio, no contiene letras, es demasiado corto o parece
texto evidentemente ilegible, el backend no debe crear la cita ni emitir una
notificacion. Debe conservar la solicitud pendiente y pedir al paciente que describa
el motivo con sus propias palabras.

### RF-1308 - Evaluacion estructurada

Cuando el texto supera las reglas locales, el evaluador puede solicitar al LLM una
respuesta JSON con `quality`, `category`, `priority_signals`, `priority_signal_evidence`
y `confidence`. El
backend acepta `valid` con una categoria soportada distinta de `unknown` o
`out_of_scope` y una confianza minima de `0.75`. Una categoria oftalmologica
`visual_symptom`, `follow_up`, `routine_exam` o `procedure` con esa confianza
identifica un motivo suficiente aun si el modelo responde `needs_clarification`.
Un respaldo local positivo para expresiones completas de molestias/problemas
oculares y revisiones generales puede aceptar el texto cuando el modelo discrepa,
tiene baja confianza o falla. Fuera de ese respaldo, baja confianza y errores
conservan la solicitud pendiente, pero reciben respuestas diferenciadas.

El LLM no puede devolver el motivo de la cita, diagnosticar ni crear la cita. Las
señales se limitan a una lista de codigos soportados y solo se conservan cuando el
texto del paciente contiene evidencia compatible. Una señal de prioridad no bloquea
la cita durante este MVP, pero se registra en el contexto de la conversacion.
Cada interpretacion semantica requiere una cita literal del motivo bajo
`priority_signal_evidence` (`{signal, quote}`), sin exigir que coincida con palabras
clave. Las reglas locales siguen aportando señales aunque el LLM las omita o no
devuelva evidencia; no se modifica el texto persistido del motivo.

### RF-1309 - Estado de evaluacion

Mientras la solicitud este pendiente, el backend conserva el numero de intentos y la
ultima evaluacion con su resultado, categoria, señales, confianza y fecha. Cuando la
cita se completa, conserva esa evaluacion bajo `last_appointment_reason_evaluation`
y elimina solamente el estado pendiente.

### RF-1314 - Motivo general suficiente

Una descripcion comprensible de una consulta oftalmologica basta para agendar.
`Tengo problemas en el ojo izquierdo`, `Tengo molestias en la vista` y
`Revision general` no deben rechazarse por no especificar diagnostico, sintoma,
intensidad ni duracion. Acompañar un motivo con `como siempre` no lo convierte
en una referencia ambigua sin contenido. El respaldo local es positivo y acotado: no reemplaza la
evaluacion semantica del resto de las expresiones ni acepta negaciones, motivos
ajenos o instrucciones mezcladas por contener la palabra `ojo`.
El motivo persistido conserva el texto del paciente, normalizando solo espacios.

### RF-1315 - Incertidumbre y fallo tecnico

Un fallo de llamada o una respuesta malformada se registra como fallo tecnico.
Si no existe respaldo local suficiente, se informa del problema tecnico, se
conserva el horario pendiente y se permite reenviar el mismo texto sin exigir
reformularlo. No se atribuye el error a la claridad del paciente.
Una evaluacion de baja confianza sin respaldo suficiente expresa incertidumbre
de la evaluacion y pregunta si la consulta es una molestia, revision o seguimiento.
No se afirma que el motivo este fuera de alcance cuando esa clasificacion tiene
baja confianza. Ninguno de esos rechazos crea una cita ni una notificacion.

### RF-1316 - Aclaracion progresiva

Un motivo legible insuficiente recibe una pregunta que cita el texto recibido;
una referencia como `Lo de siempre` se reconoce como referencia a una consulta
anterior. Sus variantes introductorias o de cortesia (`Es por lo de siempre`,
`Lo de siempre, por favor`) tampoco identifican un motivo, incluso con el evaluador
LLM desactivado. La primera aclaracion pregunta que desea revisar; a partir del segundo
intento ofrece revision, seguimiento o molestia ocular. A partir del tercero
explica que no hace falta diagnostico ni detalles clinicos y ofrece ejemplos de
respuesta general, manteniendo las opciones de molestia, revision y seguimiento.
Respuestas legibles pero insuficientes como `ok` o `Si` se citan como texto recibido,
sin presentarlas como ilegibles. Un texto ilegible pide reescribirlo sin afirmar haberlo entendido.
La progresion usa el contador persistido, sobrevive reinicios y conserva el horario.

### RF-1310 - Señal de prioridad sin diagnostico

Para el motivo actual que refiera ojos rojos, perdida repentina de vision, dolor ocular,
golpe o trauma, contacto con sustancias quimicas, sangrado, destellos, secrecion ocular
amarillenta, verdosa o abundante u otra alteracion
visual importante, el backend debe conservar una señal de prioridad operativa. La señal debe
usar un codigo soportado y una descripcion como `El paciente refiere ojos rojos que
podrian requerir atencion prioritaria.`; no debe nombrar glaucoma, desprendimiento ni
otra enfermedad.

Las señales del evaluador previo a agendar deben estar respaldadas por el motivo.
La notificacion incorpora tambien mensajes del paciente de la gestion actual, sin
heredar sintomas de citas anteriores ni usar palabras del asistente como evidencia.
Pocas lagañas al despertar y sintomas negados no fuerzan una señal.

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
8. Una respuesta estructurada con baja confianza sin respaldo local pide aclaracion
   expresando incertidumbre y no crea la cita; una categoria fuera de alcance solo
   se afirma cuando tiene confianza suficiente y no hay respaldo local contradictorio.
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
17. `Tengo los ojos rojos` registra `eye_redness` y la notificacion incluye la
    descripcion aprobada, sin aceptar texto arbitrario como `cita confirmada` en la
    seccion de señales.
18. Una cita actual con motivo `Tengo lagañas en los ojos` no hereda `eye_redness` de
    una cita anterior por ojos rojos en la misma conversacion.
19. `Tengo laga;as muy amarillentas y grandes en los ojos` registra `ocular_discharge`
    aunque el LLM omita la señal, sin cambiar el motivo del paciente.
20. Una perdida visual expresada sin las palabras clave locales puede registrar un
    codigo soportado cuando el modelo aporta evidencia literal del motivo.
21. `Asael Ponce jhbashkda` y `Asael Ponce junajusndqwd` piden aclaracion mostrando
    todas sus partes; no guardan un nombre parcial ni crean una cita/notificacion.
22. `Asael Ponce Silva` despues de esa aclaracion muestra y guarda el nombre completo;
    un motivo valido crea una sola cita en el horario original y la notificacion usa
    `Nombre: Asael Ponce Silva`, sin las partes de prueba en ese campo.
23. Un apellido inusual señalado por la heuristica puede confirmarse explicitamente
    despues de reiniciar el servicio; se guarda integro y no se interpreta `Si` como
    nombre literal, motivo ni autorizacion para crear una cita.
24. Acentos, apellidos compuestos, apostrofos, guiones, apellidos cortos y nombres
     escritos en alfabetos no latinos se conservan sin correcciones automaticas.
25. `Tengo problemas en el ojo izquierdo` crea una unica cita con ese motivo aunque
    el modelo pida detalle, tenga baja confianza o devuelva un formato invalido.
26. Una descripcion general reconocida semanticamente con una categoria oftalmologica
    y confianza suficiente crea la cita sin exigir mas detalle clinico.
27. Un fallo tecnico sin respaldo local conserva el horario y permite que el mismo
    texto, despues de reiniciar el servicio, cree una sola cita al recuperarse el evaluador.
28. Las aclaraciones del segundo y tercer intento cambian la pregunta y permiten
    completar la cita con `Revision general`, sin repetir nombre ni horario.
29. Motivos negados o ajenos a la consulta no se aceptan por coincidencias aisladas
    de palabras del respaldo local.

## Fuera del alcance

- Clasificacion clinica o diagnostico del motivo.
- Validacion medica del texto del paciente.
- Triage clinico automatico o instrucciones de emergencia.
- Politica clinica para operar señales de prioridad con pacientes reales.
- Confirmacion interactiva adicional de la creacion despues del motivo (la aclaracion
  de la escritura del nombre no autoriza por si sola una cita).
- Botones o plantillas especiales de WhatsApp.
