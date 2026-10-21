# Confirmacion de voz tras turnos VAD cancelados — 2026-10-20

## Reproduccion observada

La sesion de prueba mas reciente preparo tres propuestas de reserva. Cada pregunta
se genero y emitio completa; las tres llamadas a `confirm_appointment_action`
devolvieron el mismo rechazo:

```text
La pregunta no se emitio completa, expiro o la decision no pertenece al turno posterior. Prepara otra propuesta.
```

La llamada termino por hangup, sin fallo de OpenAI y sin crear ninguna cita. Los
datos de paciente y motivo se omiten de esta evidencia. La base no conserva el
estado booleano `armed` ni el turno de cada llamada a herramienta, por lo que se
aislo el guard concreto en la ruta de sesion en vez de atribuir al proveedor un
detalle que no persiste.

## Bucle de diagnostico y causa

Reproduccion determinista en la Raspberry:

```bash
.venv/bin/python -m unittest discover -s tests -p test_voice_session.py \
  -k confirmation_recovers_after_intermediate_voice_response_is_interrupted -v
```

Antes del cambio, ejecucion repetida: **FAIL** con el mismo texto de rechazo. El
caso minimo crea una reserva, emite/drena por completo la pregunta, consolida un
turno VAD breve, cancela su respuesta al iniciar el siguiente turno y procesa la
afirmacion en ese turno posterior. Al llegar a la llamada, la propuesta seguia
armada y dentro de vigencia, pero la secuencia habia avanzado dos turnos. El
validador exigia exactamente `pending.channel_turn + 1` y trataba el salto como
fallo terminal de la gestion.

Hipotesis verificadas:

1. Salto de secuencia por respuesta intermedia cancelada: confirmado por la
   reproduccion y las precondiciones `armed=true`, secuencia `+2`, no expirada.
2. Carrera de emision/no armada: descartada para este patron; la pregunta drenada
   conserva autorizacion armada.
3. Expiracion de diez minutos: descartada; el test llega inmediatamente.

## Correccion y regresion

Una confirmacion con ID/canal propietarios que llega sin cumplir el turno
inmediato ya no produce error terminal ni ejecuta la mutacion. El backend invalida
esa accion, revalida nombre/motivo/horario y disponibilidad, prepara un ID nuevo y
devuelve otra `confirmation_required`. Hace falta emitir completa la pregunta
nueva y recibir otra afirmacion en el turno siguiente. ID ausente/ajeno y otro
canal no renuevan la propuesta.

La prueba de regresion reproduce el patron y verifica que el primer intento no
agenda; completa el ciclo solo con la nueva pregunta y otra afirmacion. Tambien
se actualizo la cobertura de preguntas sin emision, turno equivocado y expiracion:
esas condiciones renuevan una autorizacion nueva, nunca la ejecutan directamente.

Pruebas focalizadas en la Raspberry: **33 correctas** (`test_voice_session` y
`test_voice_tools`). Regresion total: **459 correctas en 65.898 s**.
`scripts/verify_lab_controls.py` paso en Chromium/WebRTC real con proveedor falso:
cero errores JavaScript, historial voz/texto compartido, reintentos sin duplicados
y cero llamadas externas.

## Despliegue

Se sincronizaron codigo, pruebas y SDD al mirror. La reproduccion y tests usaron
agenda/proveedor falsos; antes del reinicio no habia llamadas activas. No hay una
unidad systemd del proyecto. Se reinicio solo el listener verificado de laboratorio:

| Proceso | PID previo | PID nuevo |
| --- | --- | --- |
| Laboratorio Realtime, loopback 8001 | 563829 | 633510 |

La configuracion efectiva conserva maximo de 300 s e inactividad de 30 s.
`GET /lab/health` devolvio HTTP 200 y el modo Realtime; `/lab` y `/lab/history`
respondieron 200 en la Pi. Pagina y salud tambien respondieron 200 por el forwarding
SSH en Mac. No se inicio otra llamada de pago durante estas verificaciones.

Para probar de nuevo con voz, recarga `http://localhost:8001/lab` e inicia una
llamada nueva: las sesiones anteriores terminaron sin cita y no se pueden reanudar.
