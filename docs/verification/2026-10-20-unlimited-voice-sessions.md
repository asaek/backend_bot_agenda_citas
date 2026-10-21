# Sesiones ilimitadas en el perfil de pruebas — 20/10/2026

## Alcance

El usuario solicito desactivar temporalmente el maximo total de sesiones mientras
prueba la voz Realtime. El perfil de la Pi ya habia alcanzado 5/5. El valor sigue
persistido en `.env`; reiniciar no borra sesiones anteriores.

`VOICE_MAX_SESSIONS=unlimited` ahora se interpreta como `maximum_sessions=None`.
El default para otros entornos permanece en 5. Los topes por sesion (300 s),
inactividad (30 s), una llamada concurrente, las confirmaciones y la reclamacion
durable permanecen activos. No se implementa todavia una cuota diaria; se requiere
antes de uso operativo.

## Verificacion

- La regresion de configuracion confirma que el default es 5, `unlimited` elimina
  solo el maximo total y valores fuera del rango aceptado siguen fallando.
- La regresion del repositorio crea siete sesiones de un perfil con maximo `None`;
  las siete terminan persistidas sin recrear la base.
- Suite completa en la Pi: **466 tests en 64.013 s, OK**.
- La configuracion local y la de la Pi coinciden en `VOICE_MAX_SESSIONS=unlimited`;
  el `.env` remoto conserva modo `600`.
- El proceso nuevo PID `834694` carga `VOICE_MAX_SESSIONS=unlimited`,
  `RealtimeSettings.maximum_sessions is None`, `audio_mode=realtime` y
  `calendar_provider=google`.
- `/lab/health` y `/lab` responden HTTP 200 desde la Pi y desde el Mac. No se inicio
  una conversacion Realtime de pago ni se creo una cita de Google durante esta
  verificacion.

El entorno de pruebas tiene ahora sesiones ilimitadas, no una cuota de gasto.
Definir un maximo diario requiere acordar su periodo, zona horaria y politica de
consumo antes de conectar el flujo a pacientes operativos.
