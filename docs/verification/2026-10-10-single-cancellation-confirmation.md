# Verificacion de una confirmacion de cancelacion

## Alcance y reproduccion

10 de octubre de 2026. La conversacion listaba dos citas del lunes 12/10/2026,
a las 10 AM y 12 PM. Tras `quisiera cancelar la de las 10 am`, el primer
`si por favor` devolvia una segunda pregunta de confirmacion.

La regresion del servicio reprodujo el fallo con proveedores falsos y reloj fijo:

```text
python -m unittest test_conversation_continuity.ConversationContinuityTests.test_reported_cancellation_uses_one_confirmation_after_listing_monday_appointments -v
FAILED: se esperaba 'Tu cita ha sido cancelada.' y se recibio otra pregunta de confirmacion.
```

La primera pregunta era texto del LLM sin una accion pendiente en el backend.
La afirmacion ya se clasificaba como `confirmed`; al recibirla, el LLM solicitaba
por primera vez la herramienta y el backend creaba su confirmacion real.

## Correccion y verificacion funcional

Una cancelacion directa consulta la agenda, resuelve una unica cita del paciente
y guarda `PendingAppointmentAction` antes de devolver la pregunta canonica.
El primer `si por favor` ejecuta esa accion. La fecha explicita prevalece sobre
el contexto del listado; minutos y AM/PM conservan su significado. Una referencia
no coincidente o varios objetivos no se sustituyen por otra cita.

Las preguntas textuales reconocibles de confirmacion sin estado se sustituyen
por una aclaracion de dia/horario. Una afirmacion aislada no permite al LLM crear
una cancelacion desde el historial. Se reviso directamente el diff contra el SDD;
las revisiones delegadas fueron interrumpidas y no se consideran completadas.

Se agregaron seis regresiones:

- Conversacion original, reinicio del servicio e historial acotado: una afirmacion
  cancela la cita de las 10 AM y conserva la de las 12 PM.
- Dia distinto, minutos diferentes y varios objetivos sin seleccion por defecto.
- Dia explicito, fecha numerica, ambiguedad y respuesta negativa sin mutacion.
- Pregunta textual sin estado y llamada tardia del LLM tras una afirmacion aislada.
- Peticiones directas frente a preguntas informativas, negativas y abandono.
- Webhook con duplicados de solicitud/afirmacion: una pregunta, una cancelacion,
  una notificacion al doctor y ninguna gestion antigua recuperable.

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -m unittest discover -s /home/asaek/Downloads/chatbot_test_repo/tests -q
Ran 359 tests in 18.967s
OK
SYNTAX_OK 55 files
```

Las pruebas usan SQLite temporal y proveedores falsos; `git diff --check` paso.

## Despliegue y bloqueo de autenticacion

Los archivos se sincronizaron a la Raspberry antes de ejecutar las comprobaciones.
Se copio el `.env` completo y se verifico igualdad byte por byte y modo `600`.
No se encontraron unidades systemd del proyecto. Se verificaron PID, directorio
y puerto antes de reiniciar Uvicorn desde la raiz del mirror. La configuracion
del nuevo proceso coincide con `.env`; se conservo el ngrok existente.

```text
ENV_FILE_MATCH True MODE 0o600
RUNTIME_ENV_MATCH True
local  GET /                 -> 200, cuerpo esperado
local  GET /webhook/whatsapp  -> 200, desafio esperado
local  POST /webhook/whatsapp -> 200, {"status":"ok"}
public GET /                 -> 200, cuerpo esperado
public GET /webhook/whatsapp  -> 200, desafio esperado
public POST /webhook/whatsapp -> 200, {"status":"ok"}
META_AUTH -> 401, code=190, subcode=463
```

En esta comprobacion inicial, Meta informo que el token de envio habia expirado.
El codigo estaba cargado y las rutas saludables, pero quedo pendiente actualizar
`WHATSAPP_ACCESS_TOKEN` en el `.env` local y verificar la autenticacion. La
recuperacion se registra a continuacion. Los secretos y hashes se omiten.

## Recuperacion de autenticacion - 11 de octubre de 2026

Una nueva solicitud `local to raspberry` transfirio el `.env` completo actualizado.
Se verificaron igualdad byte por byte y modo `600`. El backend y ngrok estaban
detenidos y no habia unidades systemd del proyecto; se iniciaron desde las rutas
documentadas y se comprobaron PID, directorio, puerto y configuracion efectiva.

Las comprobaciones HTTP mediante `curl` verificaron salud y ambos metodos del
webhook local y publico con codigo `200` y sus cuerpos esperados. Los POST usaron
eventos vacios. La lectura autenticada del recurso de numero de WhatsApp tambien
devolvio `200` y el recurso configurado.

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

El bloqueo de autenticacion queda cerrado. Esta recuperacion actualiza la
configuracion y la evidencia operativa; las 359 pruebas funcionales del corte
mantienen la verificacion registrada anteriormente.
