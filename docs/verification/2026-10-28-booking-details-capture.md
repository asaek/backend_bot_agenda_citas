# Verificacion - Captura conjunta de nombre y motivo

Fecha: 28/10/2026. Ejecucion en Raspberry Pi, despues de sincronizar desde el
checkout local. Referencias: spec 013, RF-1318 y ADR 0063.

## Reproduccion y causa

Se crearon tres regresiones sobre `ConversationService`, SQLite temporal y agenda
falsa, con las respuestas del agente fijadas para reproducir las conversaciones
reportadas. El comando inicial fue:

```sh
.venv/bin/python -m unittest discover -s tests -p test_booking_details_capture.py -v
```

Antes de la correccion: **3 pruebas, 3 fallos**, en 0.281 s. Los sintomas fueron:

1. `Guardé tu nombre completo como ‘Asael Ponce Silva y el motivo es por problemas de la vista’...`
2. Despues de recibir el motivo y luego el nombre, se volvia a preguntar el motivo.
3. Despues de que el agente agradecia el nombre y recibia el motivo, el backend
   volvia a preguntar `Antes de agendar tu cita, ¿cuál es tu nombre completo?`.

La captura tomaba todo el mensaje como nombre y la entrada tardia al flujo backend
ignoraba respuestas a preguntas previas del agente. No era un rechazo clinico del
motivo `problemas de la vista`.

## Correccion y regresiones

- Separacion literal de nombre y motivo conjuntos, incluyendo prefijos de nombre,
  motivo primero con etiqueta y clausula de sintoma tras el nombre.
- Conservacion de motivos de varias clausulas, incluido `Soy diabético y tengo
  problemas en la vista`, sin convertirlos en un nombre. Los prefijos se reconocen
  como palabras completas: `Soyoung Kim` se conserva integro.
- Recuperacion de respuestas contiguas del paciente a preguntas enviadas de la
  misma captura, con limite de diez minutos e independencia del historial del LLM.
- Persistencia de motivo/procedencia mientras falta aceptar el nombre, tambien
  tras un reinicio o al confirmar un nombre inusual.
- Evaluacion estructurada comun antes de crear; un motivo ajeno y una respuesta
  vacia posterior no pueden crear la cita ni reutilizar un rechazo como motivo nuevo.
- Ausencia de datos inferidos de agradecimientos del agente o heredados de una
  captura abandonada, vencida o una cita terminada.
- Los tres ejemplos pasan por el webhook con cliente de WhatsApp falso: una cita,
  confirmacion al paciente y un solo aviso al doctor ante una entrega duplicada.
  El aviso contiene el nombre separado y el motivo real, nunca `Inventado` del tool call.

La prueba de webhook es
`test_main.WebhookTests.test_booking_capture_examples_confirm_and_notify_once_on_webhook_retries`.

## Suite completa

```sh
.venv/bin/python -m unittest discover -s tests
```

Resultado final: **571 pruebas correctas**, en 87.651 s. Incluye 16 pruebas de captura
y la prueba de webhook con tres escenarios. La suite emite mensajes de fallos
inyectados y advertencias de dependencias/recursos; el resultado final es `OK`.
`git diff --check` tambien termina sin errores.

## Comprobacion adicional con IA real

Se uso el proveedor LLM configurado y su evaluador estructurado sobre bases SQLite
temporales y una agenda falsa, fijando el reloj al 28/10/2026. Los tres escenarios
conservaron nombre, motivo y horario, crearon una sola cita y emitieron un evento.
No se llamo al transporte de WhatsApp ni a Google Calendar en esta comprobacion.

Para el tercer caso se incluyo el antecedente de fecha y horarios ofrecidos. El
fragmento aislado sin ese antecedente produjo dos respuestas vacias de OpenAI;
con el contexto previo completo, el proveedor devolvio respuestas `completed` y
la captura termino correctamente. No se modifico la configuracion del proveedor
para esa prueba.

## Mirror y backend

- Codigo, pruebas y SDD sincronizados; se excluyeron `.git`, entornos, caches y datos.
- `.env` completo copiado, igualdad byte por byte comprobada en memoria y modo `600`.
- Sin servicio de proyecto detectado; se verificaron PID, comando, directorio y
  puerto antes de terminar exclusivamente el listener Uvicorn y arrancar uno nuevo
  desde `/home/asaek/Downloads/chatbot_test_repo`.
- Configuracion efectiva del listener nuevo igual a `.env`, sin mostrar valores.
- Health `GET /`: HTTP 200 y `{"status":"ok"}`.
- Webhook GET local y publico: HTTP 200 y challenge esperado.
- Webhook POST local y publico con evento vacio: HTTP 200 y `{"status":"ok"}`.
- Autenticacion de WhatsApp mediante GET de solo lectura `fields=id`: HTTP 200.
- El tunel ngrok existente se conservo y se verifico por sus rutas publicas.

Las comprobaciones HTTP usan `curl` con secretos transmitidos por configuracion
en stdin, sin incluirlos en argumentos ni salida. No se añadieron logs de depuracion
al codigo de produccion ni se hicieron commits.
