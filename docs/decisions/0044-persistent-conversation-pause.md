# ADR 0044 - Pausa persistente y seleccion contextual de horarios

## Estado

Aceptada. Reemplaza parcialmente ADR 0041 para preguntas informativas y saludos.

## Contexto y decision

La palabra `agendame` interpretaba una seleccion de horario como una nueva gestion,
eliminando la disponibilidad pendiente. Ademas, descartar una reserva al preguntar
por el costo obligaba a comenzar de nuevo. El paciente debe poder conversar sobre
otro tema, retomar su avance o desistir sin efectos de agenda.

Una seleccion completa y contextual como `agendame a las 11 am` continua la lista
ofrecida. Una hora dentro de `cancela mi cita de las 11` no es una seleccion. Una hora
no ofrecida pide aclaracion y conserva el estado. Las preguntas informativas y saludos
pausan; una nueva gestion explicita de agenda o una peticion de olvidar la anterior
la reemplaza; el abandono explicito elimina la solicitud.

La seleccion contextual de reserva admite tambien `quisiera una cita a las 9 am`
y variantes con `quiero`, `necesito`, `deseo` o `me gustaria`, con o sin verbo de
agendar. El reconocimiento sigue anclado a una expresion completa: una fecha
adicional o `otra cita` no se consume como eleccion del mismo dia. Esta regla
evita perder la disponibilidad y recibir una captura textual del nombre del LLM
sin estado persistido. El nombre aceptado pertenece a esa reserva y no se vuelve
a pedir al recibir el motivo, incluso tras reiniciar con historial acotado.

La seleccion contextual de reprogramacion tambien reconoce expresiones completas
como `quisiera cambiarla a las 12 pm`, preferencias, verbos de movimiento y peticiones
corteses. Estas referencias a la cita activa no inician otra gestion. Los periodos
incompletos, como `12 p,`, solo piden aclaracion y conservan la disponibilidad;
no generan una confirmacion. Mediodia se interpreta como 12:00 PM en el dia ofrecido.
Otra cita o fecha sigue siendo una gestion nueva, y `¿12 pm?` expresa incertidumbre.

La seleccion completa admite tambien puntuacion accidental entre palabras, como
`QUisiera.a las 10 am`, y los cierres `esta bien/me parece bien`. Se reparan esos
separadores para reconocer la frase sin modificar horas como `10.30`, ni quitar
signos de pregunta o instrucciones adicionales. La comparacion usa la hora del
texto original y los slots persistidos.
El reconocimiento, la lectura de hora y la deteccion del periodo comparten la
misma reparacion de puntuacion; `10 de.la.noche` conserva las 10 PM aunque la
lista solo ofrezca las 10 AM.
Tanto reserva como reprogramacion distinguen
hora reconocida no ofrecida, ambiguedad AM/PM y ausencia de hora valida; no disponibilidad
no equivale a no comprender la hora. Estas aclaraciones conservan el estado y no
crean una cita ni autorizan una reprogramacion. Elegir un horario para cambiar una
cita sigue requiriendo una confirmacion posterior.

El backend mueve un snapshot tipado a `paused_conversation_workflow` dentro del
contexto SQLite existente. Conserva una sola gestion, el paso y datos recibidos,
sin ampliar el historial del LLM ni incorporar memoria semantica. El prompt recibe
un recordatorio operativo construido por el backend; la recuperacion depende del
snapshot, no del recuerdo o una respuesta textual del modelo.

`Retomemos la cita` recupera el paso pendiente. Una fecha u hora claramente esperada
tambien puede retomarlo; nombres y motivos no se adivinan mientras la gestion esta
pausada. Pausar no renueva la vigencia de los horarios. Al retomar una lista o reserva
vencida se consulta nuevamente la disponibilidad y se conserva el nombre recibido
para esa misma reserva, incluso si es necesario elegir otra fecha.

Las confirmaciones se guardan solo como intencion inactiva durante la pausa. Al
retomar se resuelve nuevamente la cita, se comprueba el horario de reprogramacion y
se emite una confirmacion nueva. Un fallo de agenda conserva la accion inactiva;
un `Si` durante otro tema no la ejecuta. El backend intercepta mutaciones que el
modelo solicite al responder un tema informativo mientras existe una gestion pausada.

## Consecuencias

- La pausa sobrevive a reinicios y al recorte del historial.
- La disponibilidad guardada no bloquea un espacio en el calendario.
- No se mantienen pilas de gestiones ni confirmaciones reutilizables.
- Una nueva reserva pide nombre de nuevo; retomar la misma no repite un nombre recibido.
- Las reglas locales reconocen expresiones explicitas; mensajes ambiguos requieren
  aclaracion y no autorizan operaciones.
