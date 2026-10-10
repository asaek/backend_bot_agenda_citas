# Verificacion de seleccion con puntuacion y horarios no disponibles

## Fecha y alcance

10 de octubre de 2026. Reconocimiento de selecciones naturales con puntuacion
accidental y cierres de aceptacion; respuestas distintas para hora no disponible,
hora invalida y ambiguedad AM/PM. Cambios locales y ejecucion en Raspberry Pi.

## Reproduccion y causa

La regresion `test_reported_ten_am_choices_select_an_available_slot_after_a_nine_am_booking`
fijo el reloj al 10/10/2026, creo una cita el lunes 12/10 a las 9 AM y verifico
que una nueva lista excluia las 9 AM y seguia ofreciendo las 10 AM. Antes de la
correccion, las dos selecciones reportadas devolvian el mismo rechazo:

```text
python -m unittest test_conversation_continuity.ConversationContinuityTests.test_reported_ten_am_choices_select_an_available_slot_after_a_nine_am_booking -v
QUisiera.a las 10 am -> No identifiqué una hora de la lista.
a las 10 am esta bien -> No identifiqué una hora de la lista.
FAILED
```

La lectura de hora ya devolvia `(10, 0)` para ambas frases. El reconocimiento
completo de seleccion las rechazaba por el punto entre palabras o el cierre
`esta bien`, por lo que no llegaban a la captura backend del nombre.

Una segunda regresion reprodujo que elegir las 9 AM ocupadas o una hora fuera de
la lista de reserva tambien devolvia `No identifique`. La aclaracion de reserva
no distinguia disponibilidad, a diferencia de la rama de reprogramacion.

## Correccion y revision

- El reconocimiento acepta separadores accidentales entre palabras y cierres
  `esta bien/me parece bien`, conservando limites de frase y signos de pregunta.
- Reserva y reprogramacion comparten la aclaracion de slots: una hora valida con
  cero coincidencias informa no disponibilidad; varias coincidencias piden AM/PM;
  una entrada invalida pide aclaracion sin afirmar que esta ocupada.
- Estas respuestas conservan la lista activa o pausada y permiten una seleccion
  valida posterior sin crear citas ni emitir eventos durante la aclaracion.
- La revision independiente detecto que `10 de.la.noche` podia reconocerse pero
  perder su periodo al comparar slots. Se reprodujo en rojo con solo 10 AM ofrecidas
  y con ambos periodos. `normalize_time_selection_punctuation()` ahora se comparte
  entre reconocimiento, lectura de hora y deteccion de periodo explicito, preservando
  las 10 PM y separadores numericos como `10.30`.
- La revision final de estandares y especificacion cerro ese hallazgo sin blockers.

## Pruebas

Se agregaron siete regresiones en clasificacion, servicio y webhook:

1. Dos selecciones reportadas despues de reservar las 9 AM, con reinicio y una
   segunda cita a las 10 AM que conserva la primera.
2. Hora ocupada y horas fuera de la lista, con pausa/reinicio y eleccion valida posterior.
3. Horas invalidas, dos horas y ambiguedad entre medianoche y mediodia.
4. Puntuacion, minutos, AM/PM y cierres; preguntas y otras instrucciones fuera de la seleccion.
5. Webhook con las 9 AM ocupadas, seleccion de las 10 AM y un reintento del motivo:
   dos citas distintas y una sola notificacion por cita con el nombre correcto.
6. Periodo nocturno con puntuacion frente a una opcion diurna, en estado activo y pausado.
7. Periodo nocturno con puntuacion cuando ambas horas estan disponibles: reserva a las 22:00.

La matriz existente de reprogramacion incluye puntuacion y `esta bien`: elegir
un horario sigue pidiendo una confirmacion posterior antes de modificar la cita.

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -m unittest discover -s /home/asaek/Downloads/chatbot_test_repo/tests -q
Ran 353 tests in 18.182s
OK
SYNTAX_OK 55 files
```

Las pruebas usan SQLite temporal y proveedores falsos. `git diff --check` paso.

## Mirror y runtime

Los cambios se sincronizaron antes de cada ejecucion. El `.env` completo se copio
y comparo byte por byte en memoria, con modo `600`. Se inspeccionaron servicios,
puerto y procesos; no habia unidades del proyecto. Se termino solo el Uvicorn
verificado y se inicio un proceso nuevo desde la raiz del mirror con configuracion
fresca coincidente con `.env`. Se conservo el tunel ngrok existente.

```text
ENV_FILE_MATCH True MODE 0o600
RUNTIME_ENV_MATCH True
local  GET /                 -> 200, cuerpo esperado
local  GET /webhook/whatsapp  -> 200, desafio esperado
local  POST /webhook/whatsapp -> 200, {"status":"ok"}
public GET /                 -> 200, cuerpo esperado
public GET /webhook/whatsapp  -> 200, desafio esperado
public POST /webhook/whatsapp -> 200, {"status":"ok"}
META_AUTH -> 200, recurso esperado
```

Los POST de comprobacion usaron eventos vacios; la autenticacion de Meta se
comprobo con un GET de solo lectura. Los secretos se leyeron en memoria sin
incluir valores, hashes o encabezados en los resultados.
