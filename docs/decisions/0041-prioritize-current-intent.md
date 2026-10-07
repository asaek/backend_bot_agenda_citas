# ADR 0041 - Priorizar la intencion mas reciente sobre flujos pendientes

## Estado

Aceptada.

## Contexto

`ConversationService` resolvia estados pendientes antes de clasificar el mensaje entrante.
Una fecha, seleccion o motivo esperado podia capturar una peticion para abandonar o
cambiar de tarea, y las confirmaciones antiguas podian seguir esperando un `Si`.

## Decision

Antes de continuar un flujo pendiente, el backend clasifica el mensaje con respecto a la
tarea activa. Una respuesta esperada continua; un abandono explicito limpia la tarea sin
mutar el calendario; una intencion nueva explicita limpia el estado anterior y se procesa
por el flujo normal; una instruccion ambigua se aclara y conserva el estado. Las
confirmaciones se descartan cuando el usuario cambia de tarea.

La clasificacion es una frontera de enrutamiento, no una autorizacion para ejecutar
operaciones. Cancelar o reprogramar una cita continua requiriendo su confirmacion
explicita.

## Consecuencias

- Una tarea pendiente ya no monopoliza los siguientes mensajes del paciente.
- Los saludos y las solicitudes explicitas de olvidar la tarea tambien liberan el flujo.
- El contexto ajeno a la tarea actual permanece intacto al limpiar estados pendientes.
- Un `Si` posterior no puede autorizar una cancelacion o reprogramacion descartada.
- Los comandos ambiguos no se interpretan como mutaciones ni como abandono silencioso.
