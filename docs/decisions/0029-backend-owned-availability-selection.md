# ADR 0029 - Seleccion de disponibilidad controlada por el backend

## Estado

Aceptada.

Ampliada por ADR 0050: las expresiones no resueltas localmente pueden usar un
evaluador de IA acotado. La validacion, el estado y las preguntas siguen controlados
por el backend; las selecciones simples conservan la via sin LLM.

## Contexto

La consulta de disponibilidad ya mostraba slots reales, pero solo esperaba que el LLM
interpretara el siguiente mensaje. El LLM podia pedir el motivo como texto sin llamar
`create_appointment`; ese turno no dejaba un horario pendiente y el siguiente motivo
regresaba al agente, que podia volver a consultar disponibilidad y repetir preguntas.

## Decision

Despues de una consulta determinista de disponibilidad, `ConversationService` guardara
la fecha, los slots ofrecidos y una expiracion de 10 minutos en
`conversations.context_json`. El siguiente mensaje se resolvera contra esos slots en la
zona horaria de la agenda. Una hora valida creara directamente el estado pendiente de
`create_appointment` y usara las preguntas fijas de nombre y motivo sin invocar al LLM.

Desde la correccion del 28/10/2026, esta misma persistencia y presentacion se
aplica a consultas de un dia completo propuestas por el LLM, una vez validado
su contrato y normalizado el rango por el backend (ADR 0024). El modelo puede
interpretar una fecha no reconocida localmente; no decide los slots ofrecidos
ni redacta una lista distinta de la que queda guardada.

Una hora no ofrecida, un mensaje sin hora o un estado vencido no ejecutara la agenda.
El backend conservara la interceptacion de `create_appointment` para solicitudes con
hora exacta o tool calls que lleguen desde el agente, y las instrucciones del LLM seran
una defensa adicional, no la fuente de verdad del estado.

## Consecuencias

- La seleccion de un horario no depende de que el LLM emita un tool call.
- El paciente recibe una sola pregunta controlada por el backend para el motivo despues
  de una seleccion valida cuando su nombre ya esta registrado.
- El estado de disponibilidad puede reconstruirse despues de reiniciar el servicio.
- El parser cubre horas numericas comunes; expresiones de fecha arbitrarias quedan en
  el flujo conversacional general.
- Una disponibilidad puede quedar obsoleta durante los 10 minutos y la creacion final
  continuara siendo validada por el `ToolExecutor` y el calendario.
