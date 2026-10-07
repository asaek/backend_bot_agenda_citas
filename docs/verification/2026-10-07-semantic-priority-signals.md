# Verificacion de prioridad semantica del motivo e historial actual

## Fecha y estado

7 de octubre de 2026. Verificado en el mirror de Raspberry Pi.

## Fallo reproducido y causa

El motivo `Tengo laga;as muy amarillentas y grandes en los ojos` producia una lista
de señales vacia y `Ninguna detectada` en la notificacion. El catalogo no incluia
secreciones oculares, las señales interpretadas por el LLM se intersectaban con
coincidencias de palabras clave y la deteccion local ignoraba el historial actual.

Tras añadir la regresion y sincronizar, se ejecuto:

```text
PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -m unittest test_notification_composition.NotificationCompositionTests.test_yellow_abundant_eye_discharge_is_not_reported_as_no_priority -v
```

Resultado inicial: `Ran 1 test ... FAILED (failures=1)`; la descripcion esperada
no estaba en la lista vacia. Las regresiones semanticas y de historial tambien
fallaron antes de corregir el flujo.

## Comportamiento verificado

- `ocular_discharge` reconoce secrecion amarillenta, verdosa o abundante, incluyendo
  `laga;as`, `legañas amarillas`, `lagañas muy abundantes` y `secreción ocular verdosa`.
- El respaldo local conserva la señal aunque el modelo la omita.
- El modelo puede aportar señales sin coincidencias de palabras clave cuando devuelve
  evidencia literal del motivo o de mensajes entrantes de la gestion actual.
- El historial actual aporta sintomas aunque no se repitan en el motivo final.
- Se separan citas anteriores mediante eventos persistidos o respuestas fijas de exito
  del backend. Un evento ya encolado no corta su propio historial durante un reintento.
- Se rechaza evidencia inventada, del asistente, de mensajes futuros o que omita una
  negacion presente en la fuente. Las negaciones explicitas se excluyen del respaldo;
  una negacion posterior del mismo sintoma reemplaza su mencion previa, incluso si
  el modelo intenta reutilizar como evidencia el mensaje anterior.
- `dolor ocular sin sangrado` conserva dolor y excluye sangrado. `No puedo ver`
  conserva perdida visual. La parafrasis `Me punza el ojo sin otra molestia` admite
  dolor ocular con evidencia sin confundir la ausencia de otras molestias con una
  negacion del sintoma principal. Pocas lagañas al despertar no fuerzan prioridad.
- El cuerpo final usa descripciones aprobadas y no muestra las citas de evidencia.

## Suite automatizada

Los cambios locales se sincronizaron antes de cada ejecucion, excluyendo `.git`,
`.venv`, caches, `.env`, datos de ejecucion y archivos de respaldo.

```text
PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -m unittest discover -s /home/asaek/Downloads/chatbot_test_repo/tests -q
```

Resultado final: `Ran 255 tests in 3.331s ... OK`.

## Verificacion aislada con el LLM configurado

Se cargo la configuracion del mirror sin imprimir credenciales y se ejecutaron el
evaluador y compositor con datos de prueba, sin llamar a herramientas de calendario
ni enviar mensajes por WhatsApp.

| Caso | Resultado |
| --- | --- |
| Evaluacion del motivo de lagañas amarillentas y grandes | Aceptado, `ocular_discharge` |
| Composicion con el motivo del ejemplo | Señal de secrecion ocular, sin `Ninguna detectada` |
| Motivo `Revision de cornea`, historial `Desde hace una hora todo se volvió negro y apenas distingo las cosas` | Señal de perdida repentina de vision con evidencia semantica |
| Motivo `Revision general sin molestias` | Lista de señales vacia |

Texto observado para el ejemplo:

```text
SENALES DE PRIORIDAD
- El paciente refiere secreción ocular amarillenta, verdosa o abundante que podría requerir atención prioritaria.
```

## Runtime y HTTP

Se verificaron proceso, directorio y puerto antes de cada reinicio. La version final
quedo ejecutandose con Uvicorn PID `2328715` (PID anterior al cambio: `2282959`),
desde `/home/asaek/Downloads/chatbot_test_repo` y escuchando en `127.0.0.1:8000`.
El tunel ngrok existente estaba activo con PID `19472`.

La verificacion se hizo con `curl`; el verify token se cargo en memoria y se paso por
la entrada de configuracion de curl sin mostrarlo. Los POST usaron un evento sin
mensajes para comprobar la ruta sin producir efectos de agenda o envios.

| Ruta | Local | Publica (ngrok) |
| --- | --- | --- |
| `GET /` | `200 {"status":"ok"}` | — |
| `GET /webhook/whatsapp` | `200 12345` | `200 12345` |
| `POST /webhook/whatsapp` | `200 {"status":"ok"}` | `200 {"status":"ok"}` |
