# Etapa 1 - Confirmacion natural y aclaracion del cambio pendiente

## Alcance

12 de octubre de 2026. Puntos 1 y 2 del plan: afirmaciones completas y
deterministas, protecciones ante dudas/condiciones y aclaracion del cambio concreto.
Esta ampliacion se apoya en la confirmacion contextual existente de ADR 0049.

## Reproduccion antes de corregir

Se fijo una agenda simulada al 12/10/2026 a las 9 AM, se creo una cita para hoy
a las 11 AM y se solicito cambiarla a las 4 PM. Despues de elegir ese horario,
la regresion reinicio el servicio con historial limitado a dos mensajes.

```text
python -m unittest test_conversation_continuity.ConversationContinuityTests.test_stage_one_correct_confirmation_reschedules_on_the_first_reply -v
FAILED: 'Si es correcto' devolvia las instrucciones genericas en lugar de 'Tu cita ha sido modificada.'
```

El reconocimiento completo no incluia `es correcto`. `Si esta bien` y `Correcto,
por favor` ya se clasificaban correctamente. Añadir el vocabulario conserva la
interpretacion local y hace que el primer turno claro ejecute la accion guardada.

Las regresiones tambien detectaron que `Si, si esta bien`, `Si, si es correcto`
y `Correcto, si es correcto` podian confirmar. Se conserva el acento antes de
normalizar: un `si` posterior dentro de una respuesta afirmativa se trata como
posible condicion y pide aclaracion; un `sí` afirmativo explicito permanece valido.
Las preguntas informativas continúan por su router correspondiente.

## Aclaracion contextual

`PendingAppointmentAction.clarification_prompt()` usa el snapshot y el reloj de
agenda. En la reproduccion devuelve:

```text
No me quedó claro. ¿Confirmas cambiar tu cita de hoy a las 11:00 AM para las 4:00 PM? Responde ‘Sí’ para confirmar el cambio o ‘No’ para conservarla.
```

La aclaracion no renueva vigencia, no cambia argumentos y no consulta al LLM.
Incluye la fecha destino si cambia de dia. Se revisaron directamente implementacion,
enrutamiento y SDD; se preservaron los cambios locales previos del corte contextual.

## Pruebas

Se agregaron siete pruebas en las fronteras del clasificador, servicio y webhook:

- Afirmaciones completas con mayusculas, acentos y puntuacion.
- Condiciones, preguntas y referencias a otra fecha/cita sin autorizar la accion.
- `Si es correcto` modifica a las 4 PM en su primera respuesta tras reiniciar.
- Dudas y condiciones conservan la cita y permiten una respuesta clara posterior.
- Una negativa descarta el cambio sin modificar la agenda.
- Una afirmacion natural no renueva una confirmacion vencida.
- Las tres afirmaciones del plan recorren el webhook y sus duplicados producen
  un solo cambio y una sola notificacion al doctor.

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -m unittest discover -s /home/asaek/Downloads/chatbot_test_repo/tests -q
Ran 377 tests in 24.909s
OK
SYNTAX_OK 55 files
```

Las pruebas usan SQLite temporal y proveedores falsos. `git diff --check` paso.

## Runtime en Raspberry Pi

Se sincronizaron los cambios antes de cada ejecucion. Se transfirio el `.env`
completo, verificando igualdad byte por byte y modo `600`. No habia unidades
systemd del proyecto; se inspeccionaron directorio, proceso y puerto antes de
recargar el backend desde la raiz del mirror. Se conservo el ngrok existente.
La configuracion efectiva coincide con la copia local.

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

Los POST fueron eventos vacios y Meta se verifico con GET de solo lectura.
No se incluyeron secretos, hashes ni valores de configuracion en los reportes.
