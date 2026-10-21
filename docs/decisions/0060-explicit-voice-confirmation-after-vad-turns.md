# 0060 - Confirmacion explicita tras turnos VAD intermedios

## Estado

Aceptada el 20 de octubre de 2026 para el laboratorio de voz nativa. Sustituye
la politica de turno inmediatamente consecutivo de la seccion de saltos VAD de
ADR 0057; mantiene la confirmacion ligada a una pregunta emitida completa, a la
sesion/canal y a la accion exacta.

## Contexto

Realtime puede dividir una afirmacion hablada en varios turnos VAD. Si la respuesta
del turno intermedio se cancela, una afirmacion clara posterior llegaba al backend
con secuencia mayor que la esperada. El backend renovaba la pregunta aunque se
hubiera emitido completa y el paciente estuviera confirmando la misma reprogramacion.
La pregunta repetida podia volver a interrumpirse y dejar el flujo en un ciclo.

## Decision

- `VoiceSession` asocia cada transcripcion de entrada con el turno de audio que la
  genero. Una transcripcion tardia no se reasigna a otro turno.
- Para una confirmacion de voz que llega despues de turnos VAD intermedios, el
  backend espera hasta un segundo por la transcripcion del turno actual.
- Solo se permite la secuencia posterior si el modelo pide confirmar la accion
  pendiente, la pregunta correspondiente se emitio completa y la transcripcion de
  ese turno es una afirmacion inequivoca de la misma accion.
- Si falta la transcripcion, expira la espera, el contenido es ambiguo o la pregunta
  no se emitio completa, se renueva la pregunta sin mutar la agenda.
- Turnos antiguos, IDs/canales ajenos, otra sesion, rechazo, correccion o expiracion
  no heredan autorizacion. La transcripcion por si sola no invoca herramientas.

## Consecuencias

Una division de VAD ya no obliga a repetir datos si el turno vigente contiene una
afirmacion clara. La decision del modelo y el texto real del turno deben concordar;
si no se puede verificar dentro del plazo acotado, prevalece la confirmacion nueva
y la agenda permanece intacta. Crear, reprogramar y cancelar comparten esta regla.

## Verificacion

La regresion del flujo completo de reprogramacion cubre la pregunta emitida,
respuesta intermedia cancelada, transcripcion diferida y una sola mutacion final:
[evidencia](../verification/2026-10-20-reschedule-confirmation-vad-loop.md).
