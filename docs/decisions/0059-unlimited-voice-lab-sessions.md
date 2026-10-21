# 0059 - Sesiones ilimitadas temporalmente en el laboratorio de voz

## Estado

Aceptada el 20 de octubre de 2026 para el perfil de pruebas de la Raspberry Pi.

## Contexto

La cuota durable de cinco sesiones Realtime por perfil se agoto durante las
pruebas del cliente HTML. El usuario solicito desactivarla mientras continua la
validacion manual. Reiniciar el servidor no restablece los registros guardados en
la SQLite de voz.

## Decision

- `VOICE_MAX_SESSIONS` acepta de 1 a 100 o el valor explicito `unlimited`; si se
  omite conserva el default 5.
- El `.env` del perfil de pruebas Raspberry usa `VOICE_MAX_SESSIONS=unlimited`.
  Esto desactiva solo el maximo total de sesiones de ese perfil; se conservan los
  limites de 300 s por llamada, 30 s de inactividad, una llamada concurrente y la
  reclamacion durable de operaciones.
- No se implementa ni se configura una cuota diaria en este incremento. Antes de
  conectar pacientes operativos se debe decidir el periodo/zona horaria, persistir
  el consumo y aplicar un limite diario revisado.
- El valor de ejemplo y de otros entornos continua en 5; `unlimited` se usa solo
  en el entorno controlado de pruebas solicitado.

## Consecuencias

- El perfil de laboratorio puede iniciar mas de cinco sesiones sin recrear su base
  ni cambiar de perfil.
- La cuota total ya no limita el gasto del perfil Raspberry. La duracion, inactividad
  y concurrencia siguen acotadas, pero no sustituyen un presupuesto diario.
- Cuando se use un limite numerico y se alcance, `/lab/calls` responde HTTP 429 con
  el conteo usado/maximo. La respuesta no se presenta como fallo de microfono/SDP y
  el intento bloqueado no inicia OpenAI ni cambia el contador.
