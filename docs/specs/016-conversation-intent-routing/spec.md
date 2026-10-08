# 016 - Enrutamiento de intencion con flujos pendientes

## Estado

Verificado en Raspberry Pi con seleccion contextual y pausa persistente; evidencia
en `docs/verification/2026-10-07-conversation-pause-continuity.md`.
El corte original fue verificado en
`docs/verification/2026-10-05-conversation-intent-routing.md`.

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
