# ADR 0021 - Contexto temporal confiable para la agenda

## Estado

Aceptada e implementada.

## Contexto

El LLM no recibe automaticamente la fecha actual ni la zona horaria de la
agenda. Por eso una solicitud como "que citas tengo hoy" puede terminar en una
peticion innecesaria de la fecha exacta, listar citas de otros dias o describir
de forma ambigua una cita cancelada.

## Decision

`ConversationService` recibe el reloj y la zona horaria configurados en
`ToolExecutor` y agrega al mensaje de sistema la fecha y hora local actuales,
ademas de los rangos ISO de hoy, manana y ayer. El prompt tambien define que
`scheduled` y `confirmed` son citas vigentes y que los estados restantes no lo
son.

El adaptador LLM envia `temperature=0` para reducir variaciones de redaccion
entre solicitudes equivalentes.

El proveedor de calendario sigue siendo la fuente de verdad. El contexto
temporal solo permite que el LLM traduzca expresiones relativas a argumentos
concretos de `list_appointments`; no autoriza al modelo a inventar citas ni a
modificar la agenda.

## Consecuencias

- Las pruebas pueden fijar el reloj y verificar los rangos sin depender de la
  fecha de ejecucion.
- `GOOGLE_CALENDAR_TIMEZONE` debe configurarse con la zona horaria real de la
  agenda; `UTC` continua siendo el valor predeterminado tecnico.
- El modelo recibe instrucciones claras para separar citas vigentes de citas
  canceladas, aunque la herramienta conserve estas ultimas para consultar el
  historial.
