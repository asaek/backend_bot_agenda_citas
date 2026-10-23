# Separacion de destinatarios de notificaciones — 22/10/2026

## Alcance y hallazgo

Se audita el aviso que aparece en la conversacion del paciente antes de incorporar
plantillas. El ultimo aviso de chat usa como destinatario al doctor configurado,
pero el paciente de esa gestion usa el mismo numero terminado en `3338`. WhatsApp
presenta los dos mensajes en una sola conversacion porque corresponden a la misma
cuenta, incluso cuando los numeros se representan con prefijos mexicanos distintos.

El resultado identifica una coincidencia de roles en el escenario de prueba. Para
comprobar dos conversaciones visibles se necesita un WhatsApp de paciente distinto
del doctor; el numero del doctor configurado no requiere reemplazo.

## Configuracion efectiva y mirror

- El checksum dry-run de rsync confirma que las fuentes locales y remotas coinciden.
- `.env` local y remoto coinciden byte por byte; el archivo remoto tiene modo `600`.
- Los 28 valores administrados de `.env` coinciden con el entorno heredado de ambos
  procesos: chat PID `3965734` y laboratorio PID `3939340`.
- Ambos procesos trabajan en `/home/asaek/Downloads/chatbot_test_repo`.
- Los avisos estan habilitados y existe un doctor configurado, terminado en `3338`.

Los valores se compararon en memoria: no se imprimen tokens, credenciales, hashes,
numeros completos ni contenido de las conversaciones.

## Registros contrastados en modo de solo lectura

| Comprobacion | Resultado |
| --- | --- |
| Avisos de chat | 47 |
| Avisos de chat fuera de los doctores configurados | 0 |
| Avisos de voz (`data/calling-lab-voice.sqlite3`) | 1 |
| Avisos de voz fuera de los doctores configurados | 0 |
| Ultimo aviso de chat | ID 47, creado el 17/10 a las 22:33:34 UTC |
| Destinatario del ultimo aviso de chat | Doctor `...3338`, igual al paciente normalizado |
| Confirmacion del paciente asociada | Mensaje 928, 22:33:31 UTC, `CONFIRMACION DE CITA` |
| Contenido interno en mensajes salientes de pacientes | 0 coincidencias de los marcadores internos |
| Ultimo aviso de voz | Cancelacion del 22/10 a las 17:50:44 UTC, dirigida al doctor |

La confirmacion del paciente no contiene `RESUMEN DE LA CONVERSACION` ni
`SENALES DE PRIORIDAD`. El aviso persistido del doctor contiene ambos y comienza
con `NOTIFICACION INTERNA DE CITA`. El perfil de voz es ficticio, sin numero de
WhatsApp vinculado; su aviso tambien se dirige al doctor configurado.

## Bucle reproducible del escenario de una sola conversacion

Este contraste no envia mensajes ni modifica la agenda o SQLite:

```sh
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes asaek@192.168.1.12 \
  '/home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -B -' <<'PY'
import re
import sqlite3
from pathlib import Path
from dotenv import dotenv_values

root = Path("/home/asaek/Downloads/chatbot_test_repo")
env = dotenv_values(root / ".env")
def number(value):
    value = re.sub(r"\D", "", value)
    return "52" + value[3:] if value.startswith("521") and len(value) == 13 else value
allowed = {number(v) for v in env["DOCTOR_WHATSAPP_NUMBERS"].split(",")}
path = root / env.get("DATABASE_PATH", "data/chatbot.sqlite3")
with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
    row = db.execute("SELECT n.recipient_number,p.whatsapp_number FROM doctor_notifications n JOIN patients p ON p.id=n.patient_id ORDER BY n.id DESC LIMIT 1").fetchone()
    assert row is not None, "No hay avisos registrados"
    recipient, patient = map(number, row)
    print("notice_recipient_is_configured_doctor=" + str(recipient in allowed))
    print("notice_recipient_equals_test_patient=" + str(recipient == patient))
    assert recipient in allowed, "El aviso usa un destinatario ajeno a los doctores configurados"
    assert recipient != patient, "El doctor y el paciente de prueba usan el mismo numero"
PY
```

Resultado observado en la inspeccion equivalente del aviso 47:

```text
notice_recipient_is_configured_doctor=True
notice_recipient_equals_test_patient=True
AssertionError: El doctor y el paciente de prueba usan el mismo numero
```

El rojo expresa que no se cumple la precondicion de tener dos cuentas distintas;
no demuestra un desvio del aviso a un numero ajeno a la configuracion. El historial
conserva ese resultado mientras se contraste el mismo evento.

## Pruebas y estado de verificacion

La prueba existente de agendamiento, reprogramacion y cancelacion se ejecuto en
Raspberry y paso antes de ampliar sus aserciones. Se agregaron comprobaciones de
contenido exclusivo por destinatario y un caso con el mismo numero mexicano en
ambos roles, incluida la repeticion del webhook. Despues de sincronizar las pruebas
y documentacion desde el checkout local se ejecuto:

```sh
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes asaek@192.168.1.12 \
  'env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo/tests:/home/asaek/Downloads/chatbot_test_repo /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -B -m unittest test_main test_notification_delivery test_voice_notifications -q'
```

Resultado: **69 pruebas, OK**, en 7,695 s. Las pruebas usan SQLite temporal y
dobles de WhatsApp/LLM, sin enviar avisos reales ni repetir gestiones existentes.

Las comprobaciones HTTP posteriores, con el token de verificacion solo en memoria,
devolvieron los siguientes resultados:

| Ruta | Raspberry directa | URL publica ngrok |
| --- | --- | --- |
| `GET /` | 200, `{"status":"ok"}` | 200, mismo cuerpo |
| `GET /webhook/whatsapp` | 200, challenge correcto | 200, challenge correcto |
| `POST /webhook/whatsapp`, evento vacio | 200, `{"status":"ok"}` | 200, mismo cuerpo |

`GET /lab/health` directo devolvio 200, estado `ok`, modo `laboratory` y audio
`realtime`. El acceso SSH y el endpoint publico, inicialmente inaccesibles,
volvieron a responder al reintentar tras la confirmacion del usuario.

La consulta autenticada de solo lectura a Meta devolvio HTTP `401`, codigo `190`,
subcodigo `463` (token vencido). Este bloqueo impide acreditar un nuevo envio real
o resolver el numero emisor desde Meta en esta auditoria; no cambia la coincidencia
registrada entre paciente y doctor ni el resultado de enrutamiento local.

Las plantillas y el seguimiento persistente de callbacks siguen en el trabajo
pendiente de 011. Los registros `sent` existentes solo acreditan aceptacion inicial.

## Resultado

Los 48 avisos existentes se dirigen exclusivamente al doctor configurado. Los
cuerpos de confirmacion y notificacion interna estan separados. La conversacion
compartida observada coincide con el uso del mismo WhatsApp para paciente y doctor.
Las pruebas con cuentas distintas confirman la separacion de destinatarios; con
el numero compartido confirman dos mensajes distintos sin duplicados por reintento.
La recepcion real en dos telefonos requiere un paciente de prueba con otro numero
y credenciales Meta vigentes. Esta auditoria verifica el enrutamiento, no acredita
una nueva entrega real por WhatsApp.
