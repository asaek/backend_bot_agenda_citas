# Ciclo de confirmacion de reprogramacion por turnos VAD — 2026-10-20

## Incidencia observada

La sesion de laboratorio mas reciente preparo una reprogramacion. Dos llamadas
posteriores a `confirm_appointment_action` devolvieron otra vez
`confirmation_required`; quedaron tres acciones de reprogramacion invalidadas y
ninguna mutacion exitosa. No hubo fallo del proveedor de agenda. La inspeccion se
limito a estados, nombres de herramientas y resultados; no se copiaron
transcripciones ni datos de cita al informe.

## Reproduccion, causa y correccion

La prueba determinista `test_reschedule_confirmation_accepts_explicit_answer_after_intermediate_vad_turn`
reproduce el recorrido completo: pregunta de reprogramacion emitida, turno VAD
intermedio cancelado, transcripcion afirmativa del turno actual y herramienta de
confirmacion. Antes del cambio, la prueba fallaba porque la herramienta devolvia
otra pregunta:

```text
AssertionError: 'confirmation_required' == 'confirmation_required'
```

Comando focalizado:

```bash
.venv/bin/python -m unittest discover -s tests -p test_voice_session.py \
  -k reschedule_confirmation_accepts_explicit_answer_after_intermediate_vad_turn -v
```

La causa era la exigencia incondicional de que la confirmacion llegara exactamente
en `pending.channel_turn + 1`. Cuando VAD dividia una afirmacion y cancelaba la
respuesta intermedia, una afirmacion clara del turno vigente quedaba fuera de
secuencia y se renovaba la accion. Ademas, `VoiceSession` guardaba las
transcripciones para el historial, pero no las asociaba con el turno entregado a
la herramienta.

Ahora cada entrada de voz se correlaciona con su transcripcion. Para un salto VAD,
la sesion espera hasta un segundo por la transcripcion del turno actual. La accion
solo se ejecuta si la pregunta original se emitio completa, el modelo confirma la
misma propuesta y la transcripcion actual contiene una afirmacion inequivoca. Si
falta, es ambigua o pertenece a otro turno, se presenta otra pregunta sin modificar
la agenda. Las preguntas interrumpidas, acciones vencidas y autorizaciones de otro
canal/sesion conservan sus restricciones.

## Verificacion

- La reproduccion focalizada pasa en la Raspberry y cambia la cita exactamente una vez.
- `test_reschedule_after_vad_gap_requires_an_unambiguous_current_affirmation` pasa:
  una respuesta ambigua conserva la hora original y genera otra pregunta.
- `test_lab_continuity.py`: 11 pruebas correctas.
- Regresion completa en la Pi: **468 pruebas correctas en 65.851 s**.
- Sin llamadas a proveedores externos durante las pruebas; se usaron agenda y
  transporte falsos/mocks.

## Recarga del laboratorio

Antes de recargar, no habia sesiones de llamada o voz activas ni unidades systemd
del proyecto. Se termino solo el listener Realtime verificado, en
`127.0.0.1:8001`, con directorio de trabajo del mirror:

| Proceso | PID previo | PID nuevo |
| --- | ---: | ---: |
| Laboratorio Realtime | 866282 | 871885 |

Comprobaciones posteriores:

| Ruta/estado | Resultado |
| --- | --- |
| `/lab/health` | HTTP 200, `audio_mode=realtime`, agenda Google |
| `/lab` | HTTP 200, proveedor Google indicado |
| `/lab/history` | HTTP 200 |
| `GET /` en el backend de texto | HTTP 200, `{"status":"ok"}` |
| `GET /webhook/whatsapp` con token configurado | HTTP 200, challenge correcto |
| `POST /webhook/whatsapp` con evento vacio | HTTP 200, `{"status":"ok"}` |

La prueba con voz real queda disponible desde `/lab`; las regresiones del cambio
no iniciaron otra llamada de pago ni modificaron una cita real.
