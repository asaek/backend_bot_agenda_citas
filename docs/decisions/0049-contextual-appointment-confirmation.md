# ADR 0049 - Confirmacion contextual de la accion pendiente

## Estado

Aceptada. Amplia ADR 0037, ADR 0041 y ADR 0044 para respuestas de confirmacion.

## Contexto

Durante una cancelacion, `Cancela la cita por favor` reiniciaba la solicitud y
`Si cancelala` pausaba la gestion como cancelacion ambigua, aunque el clasificador
generico reconocia su afirmacion. El router tambien descartaba una accion al
recibir `Si, pero mejor no`, en lugar de conservarla y aclarar la contradiccion.
Aceptar cualquier texto que contenga `si` tampoco es seguro: una fecha adicional
o una condicion no debe autorizar la operacion anterior.

## Decision

`classify_action_confirmation()` reconoce expresiones completas respecto de la
herramienta pendiente antes de aplicar el router generico. Distingue una respuesta
afirmativa, negativa o incierta de un texto no reconocido, que sigue al router.
Las instrucciones de cancelar la misma cita, con pronombre o referencia generica
a `la/mi/esa/esta cita`, pueden confirmar una cancelacion ya mostrada. Nunca
inician una mutacion sin una accion pendiente.

Las fechas, horas, otras citas e instrucciones adicionales quedan fuera de ese
reconocimiento; requieren aclaracion o una nueva gestion con confirmacion propia.
Las contradicciones, condiciones no reconocidas y preguntas tentativas no autorizan
mutaciones. La resolucion no vuelve al clasificador generico como respaldo permisivo.
El reconocimiento admite hasta ocho clausulas para evitar backtracking exponencial
con fragmentos repetidos; un mensaje mas largo no se autoriza por coincidencia parcial.

La misma clasificacion se usa para enrutamiento, resolucion y pausa. Una afirmacion
durante la pausa no reactiva ni renueva la accion; retomar sigue requiriendo una
confirmacion nueva. La expiracion conserva sus diez minutos.

La ampliacion de etapa 1 admite `Si es correcto`, `Si esta bien` y `Correcto, por favor`
como respuestas completas. Antes de normalizar acentos se distingue un `si` posterior
sin acento dentro de una respuesta afirmativa, que puede condicionarla, de un `sí`
afirmativo explicito. Las preguntas informativas siguen dirigiendose al router.
Las condiciones no autorizan la accion por contener frases afirmativas conocidas.
Una duda recibe una pregunta construida desde la accion guardada, con referencia
a la cita original y al destino; la aclaracion no renueva vigencia ni pide interpretar
la intencion al LLM.

`cancela` aislado durante una cancelacion activa conserva la accion y pregunta
solo si desea cancelar esa cita. En una reprogramacion diferencia abandonar el
cambio de cancelar la cita mediante instrucciones explicitas, no una pregunta
de dos alternativas que espere `si/no`. Rechazar o abandonar la accion informa
que no hubo cambios y muestra la fecha/hora original como cita aun agendada.

## Consecuencias

- Se corrige el bucle sin nuevas dependencias, servicios, migraciones ni llamadas al LLM.
- La politica es deliberadamente conservadora: un texto fuera de las expresiones
  completas no autoriza la accion solo por incluir una afirmacion.
- La autorizacion conserva herramienta, cita, argumentos, vigencia y alcance del paciente.
- Las regresiones observan respuestas y estado/eventos de agenda, incluyendo reinicios,
  pausa, expiracion, otra cita, otra operacion y reintentos del webhook.
