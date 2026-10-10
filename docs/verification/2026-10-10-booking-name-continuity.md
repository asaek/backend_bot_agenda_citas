# Verificacion de nombre unico por reserva y respuestas conversacionales

## Fecha y alcance

10 de octubre de 2026. Seleccion natural del horario de una reserva, captura del
nombre antes del motivo, rechazo de respuestas conversacionales y continuidad
tras reinicios y reintentos. Cambios locales y ejecucion en Raspberry Pi.

## Reproduccion y causa

La prueba `test_reported_monday_booking_collects_the_name_once_and_survives_restart`
fijo el reloj al 10/10/2026 y reprodujo la conversacion de lunes a las 9 AM.
Antes de corregir, elegir `quisiera una cita a las 9 am` devolvia el saludo del
proveedor falso en lugar de la pregunta backend por el nombre:

```text
python -m unittest test_conversation_continuity.ConversationContinuityTests.test_reported_monday_booking_collects_the_name_once_and_survives_restart -v
AssertionError: 'nombre completo' not found in '¡Hola, buenos días! ¿En qué puedo ayudarte?'
```

La frase no coincidia con la seleccion contextual y se clasificaba como `switch`.
Se eliminaba la disponibilidad antes de iniciar la captura persistente del nombre;
una pregunta o agradecimiento textual del LLM no guardaba ese dato. Reconocer la
seleccion completa conserva el 12/10/2026 a las 9 AM y el flujo backend existente.
La transaccion del nombre ya conserva `name_required=false`; la regresion verifica
que ese marcador sigue sirviendo tras reiniciar con solo dos mensajes de historial.

La regresion `test_conversational_replies_are_not_saved_as_names_or_used_to_book`
reprodujo el segundo error antes de ampliar el validador:

```text
AssertionError: 'Guardé' unexpectedly found in 'Guardé tu nombre completo como ‘ya te lo habia dich’. Gracias. Ahora, ¿cuál es el motivo de la consulta?'
```

Las reglas de caracteres y sospecha de texto de prueba aceptaban frases compuestas
solo por letras. Ahora patrones de frases reconocibles descartan recordatorios,
negativas a dar el nombre y sintomas expresados como oraciones, conservando el
nombre previo, el candidato y el horario. Se mantiene la politica sin diccionario,
sin recortar apellidos y sin cambiar la escritura del paciente.

## Regresiones y revision

Se agregaron nueve pruebas en las fronteras de clasificacion, servicio y webhook:

- Conversacion original con lunes 12/10/2026, horario 9 AM, nombre y ojos rojos,
  con reinicios antes del nombre y del motivo; una sola cita y evento.
- Variantes naturales de seleccion y limites frente a otra fecha, otra cita,
  cancelacion, pregunta informativa, abandono e incertidumbre.
- Respuestas conversacionales que no reemplazan `Ana Prueba`; un nombre y motivo
  validos posteriores completan la cita en el horario original.
- Candidato `Jan Chrząszcz` conservado tras recordatorios/sintomas, reinicio y
  confirmacion explicita posterior.
- Webhook hasta una sola cita y notificacion con `Nombre: Asael Ponce Silva`,
  incluso al duplicar los mensajes de nombre y motivo.
- Reemplazo de disponibilidad pausada con `deseo/me gustaria` y otra cita/fecha.
- Preguntas de costo con esos verbos que pausan en vez de descartar la reserva,
  conservando el nombre y retomando el motivo tras reiniciar.

Las revisiones independientes de estandares y especificacion detectaron los dos
ultimos limites; se reprodujeron en rojo y se corrigieron. Los prefijos de reserva
comparten un grupo para seleccion y nueva gestion. La normalizacion para comparar
respuestas de nombre tambien es compartida y distinta del texto que se guarda.
La revision final cerro los hallazgos.

La primera suite completa detecto que una prueba antigua heredaba las notificaciones
habilitadas del `.env`. El fixture ahora desactiva explicitamente notificaciones
por defecto y cada prueba de notificacion las habilita con un doctor falso.

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -m unittest discover -s /home/asaek/Downloads/chatbot_test_repo/tests -q
Ran 346 tests in 16.825s
OK
SYNTAX_OK 55 files
```

La suite usa SQLite temporal y proveedores falsos. `git diff --check` paso.

## Mirror, configuracion y runtime

Se sincronizaron los archivos tras cada cambio antes de ejecutar pruebas en la Pi.
La copia completa de `.env` se verifico byte por byte en memoria con modo `600`.
Se inspeccionaron servicios de sistema y usuario, el puerto 8000 y ngrok; no se
encontraron unidades del proyecto. Se termino solo el PID Uvicorn verificado y
se inicio un proceso nuevo desde `/home/asaek/Downloads/chatbot_test_repo`, con
configuracion fresca coincidente con `.env`. Se conservo el tunel ngrok existente.

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

Los POST de comprobacion usaron eventos vacios. La autenticacion de Meta se
comprobo con GET de solo lectura al recurso configurado; los secretos se leyeron
en memoria y no se incluyeron en los resultados ni en esta evidencia.
