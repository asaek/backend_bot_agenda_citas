# ADR 0024 - Disponibilidad antes de elegir la hora

## Estado

Aceptada.

## Contexto

Cuando el paciente solicita una cita para un dia pero no indica una hora, el LLM
puede pedir una hora exacta en lugar de consultar los espacios libres. Esa respuesta
obliga al paciente a adivinar horarios y no aprovecha `check_availability`.

## Decision

`ConversationService` detectara solicitudes reconocibles de agenda sin hora exacta
para `hoy`, `manana`, `pasado manana` o un dia de la semana. El backend consultara
`check_availability` para todo ese dia, eliminara horarios duplicados entre
calendarios y mostrara los espacios libres antes de invocar al LLM.

Las solicitudes que ya contienen una hora exacta continuaran por el flujo normal de
creacion, incluida la pregunta obligatoria por el motivo. Las expresiones de fecha
que el detector no reconozca continuaran en el flujo del LLM.

### Correccion del 28/10/2026 - Consulta de hoy y reintentos

El detector incluye peticiones corteses como `quisiera una cita` y repara el
separador accidental de `par ahoy`/`par amañana`. Si una fecha llega mediante
`check_availability` del LLM como un dia completo, `ConversationService` valida
primero el contrato y la conduce al mismo flujo de disponibilidad. Para hoy,
el inicio se ajusta a la siguiente media hora en la zona de agenda: no se envia
medianoche pasada al ejecutor ni se debilita su rechazo de fechas pasadas.
Los rangos parciales o de varios dias conservan el ciclo normal del agente.

Una consulta fallida conserva su fecha objetivo en `PendingAppointmentDate`,
con la vigencia existente de 10 minutos. `Vuelve a intentarlo` vuelve a consultar
esa fecha, incluso tras reiniciar el servicio. Sin fecha recordada o con estado
vencido se solicita el dato; no se adivina un dia usando el historial del LLM.
La serializacion por paciente existente sigue ordenando mensajes consecutivos.

La correccion posterior de voz del mismo dia agrega el recorte de disponibilidad
restante en `ToolExecutor` (ADR 0007). Cubre tambien rangos que terminan a las
23:30 o 23:59:59 y no coinciden con el detector de dia completo. La persistencia
de la seleccion y los reintentos del chat conservan sus responsabilidades.

## Consecuencias

- El paciente recibe horarios reales antes de escoger uno.
- Una consulta de disponibilidad no crea una cita ni pregunta aun el motivo.
- La agenda y el horario laboral siguen siendo autoridad del `ToolExecutor`.
- El detector no intenta interpretar fechas arbitrarias ni lenguaje clinico.
