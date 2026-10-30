# Disponibilidad de hoy en voz

## Incidente observado

La llamada de laboratorio del 28/10/2026 a las 17:36 UTC conservo la peticion
`Quisiera agendar una cita para hoy. ¿Me puedes decir los horarios?` y respuestas
que indicaban argumentos rechazados. La auditoria de herramientas permite
contrastar directamente estas cuatro consultas:

| Inicio | Final |
| --- | --- |
| `2026-10-28T00:00:00-06:00` | `2026-10-28T23:30:00-06:00` |
| `2026-10-28T00:00:00-06:00` | `2026-10-28T23:59:59-06:00` |
| `2026-10-28T00:00:00-06:00` | `2026-10-29T00:00:00-06:00` |
| `2026-10-28T00:00:00` | `2026-10-28T23:59:59` |

Las cuatro devolvieron `ok=false`, codigo `invalid_arguments`. El inicio era
pasado en el dia actual; la consulta no llegaba a Google. La correccion previa
del chat solo interceptaba dias completos desde `ConversationService`, mientras
que Realtime usa `VoiceTools -> ToolExecutor` y tambien propone otros finales.

## Reproduccion determinista

Se agrego antes de corregir una regresion por la frontera real de `VoiceTools`,
con SQLite temporal, agenda falsa, las cuatro solicitudes capturadas y reloj
fijado al 28/10/2026 a las 11:36 de America/Mexico_City. Desde la raiz del mirror:

```text
PYTHONPATH=.:tests .venv/bin/python -m unittest \
  test_voice_tools.VoiceToolsTests.test_captured_today_availability_queries_return_future_slots -v
Ran 1 test in 0.077s
FAILED (failures=4)
```

Cada variante fallaba con el mismo codigo observado en la llamada. Despues de la
correccion, las cuatro devuelven slots desde las 12 PM sin preparar una reserva.

## Correccion

- `ToolExecutor` recorta unicamente consultas que comienzan en el dia actual de
  la zona laboral y contienen el instante presente. El inicio efectivo es la
  siguiente media hora futura; el final y el request original se conservan.
- Si no queda otro inicio de media hora dentro del rango, devuelve cero slots
  sin llamar al proveedor. Dias anteriores y rangos terminados siguen rechazados.
- El recorte se aplica despues de parsear argumentos y solo a disponibilidad.
  Crear/reprogramar conservan la validacion estricta de fechas pasadas. En voz
  se mantienen deduplicacion, identidad y limite original de siete dias.
- Las instrucciones de voz piden consultar el dia antes de capturar nombre,
  motivo o una hora exacta cuando todavia no se ha elegido un horario.

## Verificacion ejecutada en Raspberry Pi

Todos los cambios se editaron en el Mac y se sincronizaron antes de ejecutar.

```text
PYTHONPATH=.:tests .venv/bin/python -m unittest \
  test_voice_tools test_tool_executor test_availability_recovery -v
Ran 53 tests in 2.615s
OK

.venv/bin/python -m unittest discover -s tests
Ran 601 tests in 92.614s
OK
```

La suite incluye el replay de las cuatro solicitudes de voz, conversion desde
UTC y zona omitida, final de rango conservado, limite exacto de media hora,
fin del dia, rangos pasados, creaciones pasadas y regresion del chat.

Se repitieron ademas las cuatro solicitudes auditadas mediante `VoiceTools` y
el proveedor Google seleccionado por `laboratory_executor`, usando la
configuracion de la Pi y una base temporal. Cada una devolvio ocho slots futuros
con `ok=true`. Solo se consulto disponibilidad; no se modificaron citas ni se
abrieron conexiones de pago a OpenAI para este replay.

## Activacion y acceso

- Se comprobaron unidades systemd de sistema/usuario, argumentos, directorios y
  listeners. No habia servicios del proyecto ni sesiones de voz/texto activas.
- Backend operativo reiniciado: PID `188292 -> 190051`, puerto 8000.
- Laboratorio reiniciado: PID `188785 -> 190055`, puerto 8001, factory correcta,
  modo `realtime` y proveedor `google`. La configuracion efectiva de ambos
  coincide con la configuracion cargada de la Pi.
- `.env` de la Pi conservado; coincide byte a byte con el local y tiene modo `600`.
- Tunel SSH del Mac reutilizado, PID `30401`, y ngrok conservado.
- Salud y HTML del laboratorio: HTTP 200 desde Pi y Mac, sin autenticacion.
- Salud operativa, GET/POST vacio del webhook local/publico y autenticacion Meta
  de solo lectura: HTTP 200 con los resultados esperados.

La evidencia acredita la causa de la llamada, el replay por herramientas, Google
y el acceso al laboratorio. Una nueva respuesta hablada completa debe
comprobarse al iniciar otra llamada desde `http://localhost:8001/lab`.
