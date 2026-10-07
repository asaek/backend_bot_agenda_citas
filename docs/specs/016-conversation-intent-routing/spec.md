# 016 - Enrutamiento de intencion con flujos pendientes

## Estado

Verificado en Raspberry Pi. Los mensajes nuevos se clasifican antes de procesar un
flujo pendiente; la evidencia esta en
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
  citas, hace otra pregunta, saluda o pide olvidar la tarea actual.
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

Una solicitud explicita de consultar citas, agendar, consultar horarios, reprogramar,
cancelar una cita, saludar, olvidar la tarea actual u otra pregunta debe limpiar el estado
pendiente anterior y procesar el mensaje nuevo por su flujo normal. Una solicitud real de
cancelacion debe conservar la confirmacion explicita ya definida.

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

## Criterios de aceptacion

1. `no cancela mejor dejala asi` durante una seleccion de disponibilidad finaliza la
   solicitud sin crear una cita.
2. `cancela` durante una seleccion pendiente pide aclaracion y conserva la lista ofrecida.
3. `¿Qué citas tengo para hoy?` durante una seleccion pendiente llega al flujo de listado
   y elimina la lista anterior.
4. `Cancela mi cita de las 11` durante una seleccion de reprogramacion inicia el flujo de
   cancelacion y muestra su confirmacion sin cancelar la cita inmediatamente.
5. Una pregunta nueva durante una confirmacion de reprogramacion descarta esa confirmacion;
   un `Sí` posterior no mueve la cita.
6. Fechas, horarios y confirmaciones claras continuan el flujo pendiente existente.
7. Las interrupciones y aclaraciones no emiten eventos ni cambian el calendario.
8. Los datos no relacionados del contexto persisten despues de limpiar la tarea.
9. `Hola` y `Olvida lo que estás haciendo, te estoy saludando` durante una seleccion
   pendiente abandonan esa tarea y reciben una respuesta al nuevo mensaje.
