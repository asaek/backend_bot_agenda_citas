# Plantilla aprobada: prueba real entregada — 25/10/2026

## Resultado

Una unica prueba controlada de `aviso_cita_medico`, idioma `es_MX`, fue aceptada
por Cloud API y Meta confirmo **`delivered` a las 19:58:57 UTC del 25/10/2026**.
El callback se correlaciono con el ID completo devuelto por la API y el numero
del doctor terminado en `3338`; el contacto resuelto por Meta tambien coincidio.

Fue un diagnostico directo de `WhatsAppClient.send_template()` con los ejemplos
de `Paciente de prueba` proporcionados por el usuario. No se crearon/modificaron
citas ni perfiles, ni se registro una mutacion ficticia en la bandeja de avisos.
No se recupero o marco como entregado un aviso historico. Los callbacks genuinos
se conservaron en el inbox; al no existir un evento de agenda asociado a esta
prueba de transporte, no se les atribuye un aviso operativo por suposicion.

## Comprobacion previa mediante Meta

Se uso el token actualizado por el usuario y consultas autenticadas de solo lectura:

| Dato | Resultado confirmado |
| --- | --- |
| Recurso del emisor | HTTP 200 |
| WABA que contiene el emisor | `1047483564765260`, `Test WhatsApp Business Account` |
| Phone Number ID | `1371219642733635`, coincide con la configuracion |
| Emisor y doctor | Numeros diferentes |
| Plantilla | `aviso_cita_medico` |
| Idioma | `es_MX` |
| Estado | `APPROVED` |
| Formato de variables | `POSITIONAL` |
| Posiciones de cuerpo | 1 a 9 |
| Encabezado | Coincide con `NOTIFICACION INTERNA DE CITA` |
| Cuerpo | Coincide con el contrato, normalizando espacios |

El catalogo contiene ahora `aviso_cita_medico` y `hello_world`. Se resuelve la
ausencia observada el 23/10 sin cambiar el WABA ni el Phone Number ID. El candidato
de URL `2157628355165252` sigue devolviendo `100/33`, con tipo/acceso no confirmados;
esa investigacion ya no es requisito para este envio comprobado.

## Transferencia de configuracion y runtime

Se transfirio **solo `WHATSAPP_ACCESS_TOKEN`** desde el `.env` local por stdin SSH.
Se verifico su igualdad en memoria, la conservacion de otras variables y el modo
remoto `600`, sin imprimir valores ni hashes de la credencial.

Los puertos 8000, 8001 y 4040 estaban libres, sin procesos Uvicorn/ngrok ni unidades
systemd del proyecto. Se iniciaron los servicios desde la raiz del mirror:

- Backend PID `91541`, puerto 8000.
- Laboratorio PID `91550`, puerto 8001, audio `realtime`.
- Ngrok PID `91562`, endpoint publico configurado.

La configuracion efectiva de ambos Uvicorn coincide con las variables administradas
de `.env`. Laboratorio usa los overrides habituales `LAB_CALLS_ENABLED=true` y
`LAB_AUDIO_MODE=realtime`, sin alterar el archivo de configuracion.

| Comprobacion | Raspberry directa | Publica por ngrok |
| --- | --- | --- |
| `GET /` | 200, cuerpo esperado | 200, cuerpo esperado |
| `GET /webhook/whatsapp` | 200, challenge correcto | 200, challenge correcto |
| `POST /webhook/whatsapp`, evento vacio | 200, cuerpo esperado | 200, cuerpo esperado |

`GET /lab/health` devolvio 200, estado `ok`, audio `realtime`.

## Pruebas automatizadas pertinentes

Fuentes locales y espejo coinciden segun el dry-run con checksum. Sin cambios de
codigo se ejecutaron las pruebas de mapeo, callbacks y cliente HTTP:
**28 pruebas, OK**, en 1,964 s.

```sh
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes asaek@192.168.1.12 \
  'env DOCTOR_NOTIFICATIONS_ENABLED=false DOCTOR_NOTIFICATION_TRANSPORT=text PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo/tests:/home/asaek/Downloads/chatbot_test_repo /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -B -m unittest test_notification_template test_notification_statuses test_main.WhatsAppClientTests -q'
```

La ultima suite completa sigue siendo la registrada el 23/10 con 554 pruebas;
no se presenta como una suite completa repetida en esta comprobacion.

## Traza de la prueba real

```text
started_at=2026-10-25T19:58:46.461756+00:00
template=aviso_cita_medico
language=es_MX
parameter_count=9
recipient_suffix=3338
resolved_contact_matches=true
provider_message_id_suffix=I5MTdCQQA=
provider_delivery_status=delivered
provider_timestamp=2026-10-25T19:58:57+00:00
matching_callback_count=2
```

La correlacion se hizo con el ID completo en memoria, no con el sufijo. Se envio
un solo componente `body`, con los nueve valores del contrato y sin encabezado
dinamico. La prueba no requirio LLM ni operacion de agenda. Se acredita entrega
informada por Meta, no lectura humana, ni se presume la situacion exacta de la
ventana de mensajeria del doctor.
