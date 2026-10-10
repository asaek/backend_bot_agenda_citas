# 016 - Enrutamiento de intencion con flujos pendientes

## Estado

Verificado en Raspberry Pi con seleccion contextual y pausa persistente; evidencia
en `docs/verification/2026-10-07-conversation-pause-continuity.md`.
El corte original fue verificado en
`docs/verification/2026-10-05-conversation-intent-routing.md`.
La respuesta de horario de reprogramacion no disponible esta verificada en
`docs/verification/2026-10-09-unavailable-reschedule-time.md`.
La ampliacion de selecciones naturales de reprogramacion esta implementada;
las regresiones y la suite completa de 337 pruebas estan verificadas en Raspberry Pi.
El backend esta recargado y sus rutas y autenticacion de WhatsApp estan verificadas
con HTTP 200 tras actualizar la configuracion local; evidencia en
`docs/verification/2026-10-09-natural-reschedule-selection.md`.
La seleccion natural de una reserva y las preguntas de costo con verbos de agenda
estan verificadas en `docs/verification/2026-10-10-booking-name-continuity.md`.
La puntuacion, los cierres de seleccion y la no disponibilidad en reserva estan
verificados en `docs/verification/2026-10-10-booking-slot-selection.md`.

## Objetivo

Permitir que el paciente abandone o cambie una tarea de agenda sin quedar atrapado en
la respuesta que esperaba el flujo anterior.

## Alcance

- Identificar el flujo pendiente antes de procesar una fecha, horario, nombre, motivo o
  confirmacion.
- Continuar cuando el mensaje responde claramente al dato solicitado.
- Abandonar una solicitud de reserva o cambio sin crear, modificar o cancelar una cita.
- Reemplazar el flujo pendiente cuando el paciente inicia claramente otra gestion de
  citas o pide olvidar la tarea actual. Preguntas informativas y saludos pausan el avance.
- Aclarar expresiones ambiguas como `cancela` sin borrar el estado ni ejecutar una
  mutacion.
- Descartar confirmaciones pendientes al cambiar de tarea para que un `Si` posterior no
  ejecute una accion antigua.

## Requisitos funcionales

### RF-1601 - Clasificar antes de continuar

Antes de resolver cualquier estado pendiente, el backend debe evaluar el mensaje entrante
segun la tarea activa. Debe distinguir entre una respuesta esperada, un abandono, una
intencion nueva y una expresion ambigua.

### RF-1602 - Abandono sin efectos de agenda

Una expresion clara como `no, mejor déjala así` debe limpiar la tarea pendiente y
responder de acuerdo con la operacion: una reserva incompleta no crea una cita y una
reprogramacion incompleta conserva la cita original. El abandono no debe emitir eventos
ni notificaciones.

### RF-1603 - Cambio explicito de intencion

Una nueva solicitud explicita de consultar citas, agendar, consultar horarios,
reprogramar, cancelar una cita u olvidar la tarea actual debe limpiar el estado
pendiente anterior y procesar el mensaje nuevo por su flujo normal. Una seleccion
contextual de la lista, incluso con `agendame`, continua la misma reserva. Una
solicitud real de cancelacion conserva la confirmacion explicita ya definida.
Una solicitud directa que referencia `la de las 10 am` sin repetir la palabra
cita tambien inicia la gestion de cancelacion; un `cancela` aislado sigue siendo ambiguo.
La seleccion de reserva tambien admite `quisiera una cita a las 9 am` y variantes
con `quiero`, `necesito`, `deseo` o `me gustaria`, con saludo/cortesia opcionales.
Una expresion completa conserva el dia ofrecido; una fecha adicional o una solicitud
explicita de `otra cita` no cuenta como eleccion de esa misma reserva.

### RF-1604 - Cancelacion ambigua

Una expresion aislada como `cancela` debe pedir aclaracion sobre si el paciente desea
abandonar la solicitud actual o cancelar una cita existente. La cita y el estado pendiente
deben permanecer intactos hasta que la intencion quede clara.

### RF-1605 - Confirmacion no reutilizable

Si el paciente cambia a una tarea nueva mientras una cancelacion o reprogramacion espera
confirmacion, el backend debe descartar esa accion antes de atender la tarea nueva. Una
respuesta afirmativa posterior no debe ejecutar la accion descartada.

### RF-1606 - Estado restante

Limpiar una tarea debe eliminar unicamente los estados pendientes de agenda; debe
conservar el resto del contexto de conversacion y del paciente.

### RF-1607 - Pausa persistente

Preguntas informativas y saludos deben pausar el flujo y recibir una respuesta al
tema actual. El estado conservado incluye el paso, fecha, horario y datos recibidos,
y sobrevive a reinicios y al limite de historial. Existe como maximo una gestion
activa o pausada. No se permiten mutaciones del LLM mientras responde otro tema
con una gestion pausada.
Una pregunta reconocible de costo o precio, como `Cual es el costo si deseo reservar
una cita`, sigue siendo informativa aunque mencione agendar. No debe descartar la
reserva ni su nombre recibido al atenderse desde un estado activo o pausado.

### RF-1608 - Recuperacion contextual

`Retomemos la cita` y variantes claras recuperan el paso solicitado, sin repetir el
nombre si ya se recibio para esa reserva. Una respuesta clara de fecha o seleccion
tambien retoma el flujo. Un `Si` aislado no recupera ni ejecuta una confirmacion
pausada. Nombres o motivos ambiguos durante otro tema no se consumen automaticamente.

### RF-1609 - Vigencia al retomar

La pausa no renueva los diez minutos de disponibilidad. Retomar una lista o reserva
vencida consulta horarios actuales antes de aceptar una eleccion anterior. El nombre
recibido acompaña la misma reserva cuando cambia de horario o necesita otra fecha.
Retomar una cancelacion o reprogramacion resuelve la cita actual y genera una nueva
confirmacion; la reprogramacion comprueba ademas la disponibilidad del destino.
Si la lectura falla, la confirmacion anterior sigue inactiva.

### RF-1610 - Hora reconocida pero no disponible

Durante la seleccion de reserva o reprogramacion, una hora valida y reconocible
que no coincide con ninguno de los horarios ofrecidos debe responder de forma comprensible:
`Ese horario ya está ocupado o no está disponible. Elige uno de los horarios ofrecidos
o dime si prefieres dejar tu cita como está.`
No debe tratarse como una hora incomprensible ni como una nueva gestion. Se conserva
la lista y, en una reprogramacion, la cita original hasta elegir y confirmar el cambio.
Una respuesta sin hora valida pide elegir una hora; si una hora sin AM/PM coincide
con dos opciones, se aclara el periodo sin afirmar que este ocupada. Estas respuestas
no modifican la agenda ni emiten eventos de cita.
En reserva, la salida propone elegir un horario ofrecido o abandonar la solicitud,
sin preguntar aun el nombre. En reprogramacion, conserva la cita original y exige
confirmacion despues de una seleccion valida. Ambas aclaraciones se atienden
tambien desde una disponibilidad pausada, incluso despues de reiniciar.

### RF-1611 - Selecciones naturales de reprogramacion

Con disponibilidad de reprogramacion pendiente, una seleccion completa como
`quisiera cambiarla a las 12 pm`, `me gustaria moverla a las 12 pm`, `ponla a las 12 pm`
o `me viene bien a las 12 pm` continua esa gestion. Se aceptan peticiones corteses como
`¿Podrias cambiarla a las 12 pm?`, referencias a `mi cita`, elecciones de `el horario`
y cortesia o puntuacion alrededor. Se mantiene la cita original y la fecha ofrecida;
una coincidencia unica genera confirmacion sin volver a consultar la lista mediante el LLM.

### RF-1612 - Expresiones de mediodia

Expresiones como `al mediodia`, `para el mediodia`, `12 del mediodia` y
`12 del dia` seleccionan las 12:00 PM si ese horario esta ofrecido. Se usan la zona
horaria y la fecha persistidas de la gestion.

### RF-1613 - Periodo incompleto sin perdida de estado

Una seleccion con AM/PM incompleto, como `quisiera cambiarla a las 12 p,`,
pide escribir la hora completa con AM o PM sin iniciar otra gestion, crear una accion
de confirmacion ni afirmar que el horario esta ocupado. Para `12 p,` se pregunta
si se refiere a las 12 del mediodia e indica responder `12 pm`. La respuesta corregida
continua el flujo, incluso tras un reinicio. Un `Si` aislado no selecciona esa hora.

Una hora dentro de una cancelacion, una referencia a otra cita o una nueva fecha no
cuenta como seleccion del mismo dia. `¿12 pm?` sigue siendo una eleccion incierta que
pide aclaracion; una peticion cortes de moverla pide la confirmacion de la mutacion.
No se cambia la agenda hasta confirmar. La reprogramacion conserva identidad,
motivo y duracion, y solo su ejecucion exitosa emite el evento de cita.

Las aclaraciones tambien se resuelven desde el snapshot cuando la disponibilidad
esta pausada. Si medianoche y mediodia estan ofrecidos, `a las 12` pide AM o PM;
`12 am` selecciona medianoche y `12 pm` selecciona mediodia.

### RF-1614 - Puntuacion accidental y cierre de una seleccion

Una seleccion completa como `QUisiera.a las 10 am` debe reconocer las 10 AM.
`a las 10 am esta bien` y `a las 10 am está bien, gracias` tambien seleccionan esa
hora si esta ofrecida. Se admiten puntos, comas o punto y coma entre palabras,
sin cambiar separadores numericos como `10.30` ni perder un periodo como `a. m.`.
`esta bien/me parece bien` acompaña la seleccion; no es una confirmacion de mutacion.
Preguntas tentativas, otra fecha, dos horas u otra instruccion permanecen fuera
del reconocimiento de una seleccion completa.
La normalizacion se comparte con la lectura de hora y periodo: `a las 10 de.la.noche`
expresa las 10 PM. Si solo las 10 AM estan ofrecidas, informa no disponibilidad;
si estan ambos periodos, selecciona unicamente las 10 PM. Esta distincion se
mantiene tras pausar y reiniciar el servicio.

## Criterios de aceptacion

1. `no cancela mejor dejala asi` durante una seleccion de disponibilidad finaliza la
   solicitud sin crear una cita.
2. `cancela` durante una seleccion pendiente pide aclaracion y conserva la lista ofrecida.
3. `¿Qué citas tengo para hoy?` durante una seleccion pendiente llega al flujo de listado
   y elimina la lista anterior.
4. `Cancela mi cita de las 11` durante una seleccion de reprogramacion inicia el flujo de
   cancelacion y muestra su confirmacion sin cancelar la cita inmediatamente.
5. Una nueva gestion de agenda durante una confirmacion de reprogramacion la descarta;
   una pregunta informativa la pausa como intencion inactiva. Un `Sí` posterior no mueve
   la cita hasta retomar y recibir una confirmacion nueva.
6. Fechas, horarios y confirmaciones claras continuan el flujo pendiente existente.
7. Las interrupciones y aclaraciones no emiten eventos ni cambian el calendario.
8. Los datos no relacionados del contexto persisten despues de limpiar la tarea.
9. `Hola` pausa la seleccion; `Olvida lo que estás haciendo, te estoy saludando`
   descarta la gestion anterior. Ambos reciben una respuesta al nuevo mensaje.
10. `11 am`, `damela a las 11` y `agendame a las 11 am` continúan la lista ofrecida;
    `cancela mi cita de las 11` inicia cancelacion, aunque la lista contenga esa hora.
11. Una pregunta sobre costo despues de entregar el nombre no lo reemplaza ni vuelve
    a solicitarlo al retomar, incluso con un servicio reiniciado e historial corto.
12. Un horario ocupado durante la pausa no se acepta desde una lista vencida.
13. `No quiero cancelarla`, `No la modifiques` y `Ya no quiero agendar` abandonan
    la operacion correspondiente sin mutaciones ni eventos.
14. Una nueva gestion de agenda reemplaza la pausada; no queda una solicitud antigua
     recuperable con una confirmacion posterior.
15. Con una cita a las 9 AM y las 10 AM ocupadas, `Cambiala para las 10 am` y
    `a las 10` explican que el horario esta ocupado o no disponible y conservan la
    seleccion pendiente. Elegir 9:30 AM pide confirmacion antes de cambiar la cita.
16. Mensajes sin una hora valida y horas ambiguas AM/PM no se presentan como ocupadas.
17. La secuencia listar la cita de hoy a las 10, pedir modificarla y elegir
    `quisiera cambiarla a las 12 pm` muestra confirmacion del cambio 10:00 -> 12:00.
    Confirmar modifica esa misma cita una sola vez y conserva motivo y duracion.
18. Las variantes naturales, peticiones corteses y expresiones de mediodia llegan a
    confirmacion desde la disponibilidad pendiente, sin reiniciar la gestion.
19. `12 p,` pide aclaracion y conserva la seleccion; corregir a `12 pm` continua
    despues de reiniciar el servicio. La confirmacion tambien sobrevive al reinicio.
20. Una seleccion natural retoma una lista pausada vigente tras un reinicio.
21. Otra cita, otra fecha, cancelacion, abandono y preguntas informativas conservan
     su enrutamiento; una pregunta tentativa sobre la hora sigue pidiendo aclaracion.
22. Saludos antes de una peticion entre signos de pregunta y selecciones de `el horario`
    no pierden la vinculacion con la cita. AM/PM incompleto durante una pausa se aclara
    sin consultar al LLM; `a las 12` distingue medianoche de mediodia cuando ambas estan libres.
23. `Quiero dejarla como esta` abandona el cambio, una pregunta sobre donde dejar el
    coche pausa la gestion y la cortesia despues de `?` conserva una peticion de seleccion.
24. `Quisiera una cita a las 9 am` continua la lista de reserva y llega a la captura
    backend del nombre; otra cita, otra fecha, preguntas informativas y abandonos
    mantienen su enrutamiento y no se consumen como eleccion del horario ofrecido.
25. Las dos frases reportadas reconocen las 10 AM ofrecidas y no responden
    `No identifique una hora`; una seleccion de las 9 AM ocupadas si informa no disponibilidad.
26. Puntuacion, minutos, AM/PM y cierres de aceptacion mantienen su significado;
    preguntas, dos horas y otras instrucciones no se convierten en selecciones.
27. Un periodo nocturno con puntuacion conserva las 10 PM; no se sustituye por las
    10 AM ni se considera ambiguo por haber ambos periodos ofrecidos.
