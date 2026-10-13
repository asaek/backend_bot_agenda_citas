# Seleccion hibrida de horarios

## Estado

Verificado en Raspberry Pi con 389 pruebas y comprobacion del proveedor real de IA.
Backend desplegado, configuracion efectiva y rutas locales/publicas verificadas.
El cierre operativo quedo completado el 13/10/2026 al transferir el `.env` local
actualizado y comprobar autenticacion Meta con HTTP 200. Evidencia en
`docs/verification/2026-10-12-hybrid-slot-selection.md`.
Plan aprobado por el usuario el 12/10/2026.

## Objetivo

Entender selecciones naturales sobre los horarios ya ofrecidos, sin exigir una
frase exacta ni confundir la eleccion con la autorizacion de una reprogramacion.

## Requisitos y criterios de aceptacion

1. `a las 9 am estaria bien` y `si a las 9 am esta bien` seleccionan las 9 AM en
   su primer intento y muestran la confirmacion del cambio. La cita original
   permanece intacta hasta recibir una confirmacion explicita posterior.
2. Las horas simples y expresiones locales reconocidas no requieren llamadas al
   modelo. Una expresion natural no reconocida puede ser interpretada por la IA
   usando exclusivamente el mensaje actual, el paso pendiente y los horarios ofrecidos.
3. El resultado del modelo solo puede referirse a un horario de esa lista. No
   decide disponibilidad, no cambia fechas ni identifica otra cita y no ejecuta
   herramientas. El backend conserva fecha, zona, cita y vigencia del estado.
4. El enrutamiento y la seleccion consumen la misma interpretacion una sola vez
   por turno, tanto con disponibilidad activa como pausada. Retomar conserva los
   controles existentes de expiracion y refresco de horarios.
5. Condiciones, negaciones, preguntas tentativas, varias horas, otra fecha/cita
   e instrucciones adicionales no se aceptan automaticamente como seleccion.
   Las gestiones nuevas y preguntas informativas siguen su ruta existente.
   Un `Si` aislado tampoco selecciona una opcion; una cantidad como `dos horarios`
   no se confunde con otra hora y `las nueve (9 am)` puede referirse a la misma opcion.
6. Una hora no ofrecida, ambiguedad AM/PM y una hora invalida se distinguen sin
   permitir que el modelo elija una alternativa por el paciente.
7. Si el modelo falla o devuelve una respuesta invalida, se pide aclaracion y se
   conserva la gestion. Una confirmacion final sigue siendo local y contextual.
   Los fallos conservan en SQLite su tipo y codigo HTTP, sin contenido del paciente
   ni valores sensibles en el registro de errores.
8. Las pruebas del servicio y webhook comprueban el estado de agenda, reinicio,
   expiracion y duplicados: una confirmacion produce un solo cambio y notificacion.

## Fronteras de verificacion

Se reutilizan las fronteras aprobadas en el plan: `ConversationService.build_reply`
con agenda falsa y persistencia temporal, y el webhook mediante `TestClient`.
El contrato del evaluador se verifica con respuestas del proveedor falso y dobles
HTTP, sin enviar mensajes de WhatsApp ni modificar la agenda real.
