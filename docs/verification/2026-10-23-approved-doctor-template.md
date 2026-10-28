# Plantilla aprobada y renovacion del token — 23/10/2026

Antecedente historico: el 25/10/2026 la plantilla ya figura `APPROVED` en la WABA
del emisor configurado y la prueba obtuvo un callback real `delivered`. La
[evidencia posterior](2026-10-25-approved-template-delivered.md) sustituye el estado
de bloqueo para el envio actual, conservando las observaciones originales de este documento.

## Configuracion adoptada

El usuario reporta aprobada `aviso_cita_medico` en `es_MX` y proporciona su texto
y los nueve ejemplos de variables. Se configura un componente `body` con
parametros posicionales en orden: evento, fecha, horario, motivo, estado, nombre,
telefono, resumen y prioridad. El encabezado es fijo en Meta. El contrato completo
esta en `../specs/011-doctor-notifications/approved-template.md`.

`.env.example` y `.env` local usan ese mapeo. Los numeros del doctor y las
credenciales ajenas a la rotacion se conservan. La prueba de contrato usa el
compositor y HTTP simulado y compara los nueve valores proporcionados por el
usuario con el JSON real del cliente, sin encabezado dinamico ni parametros con nombre.

## Token: transferencia de alcance limitado

Tras la actualizacion local solicitada por el usuario se transfirio unicamente
`WHATSAPP_ACCESS_TOKEN`. Se leyo con python-dotenv y se envio por stdin de SSH,
sin valores en argumentos, salida, hashes publicados o archivos adicionales.

Se verifico en memoria:

```text
matches_local=true
other_settings_preserved=true
mode=0o600
```

La consulta del recurso del emisor devolvio HTTP **200**. El numero emisor
resuelto no coincide con el doctor configurado. El token informa permisos
`whatsapp_business_management`, `whatsapp_business_messaging` y `public_profile`.
Esto valida autenticacion, sin acreditar disponibilidad de la plantilla.

## Pruebas y runtime

La nueva prueba fallo inicialmente porque el ejemplo aun tenia nombre e idioma
vacios. Paso despues de adoptar el contrato proporcionado. Suite completa:
**554 pruebas, OK**, en 85,281 s, ejecutadas en Raspberry tras sincronizar.

```sh
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes asaek@192.168.1.12 \
  'env DOCTOR_NOTIFICATIONS_ENABLED=false DOCTOR_NOTIFICATION_TRANSPORT=text PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo/tests:/home/asaek/Downloads/chatbot_test_repo /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -B -c '\''import os,unittest; os.chdir("/home/asaek/Downloads/chatbot_test_repo"); result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover("tests")); raise SystemExit(not result.wasSuccessful())'\'''
```

Los overrides del proceso de pruebas evitan habilitar envios reales desde casos
que hereden configuracion del entorno. Las pruebas de plantilla habilitan y
configuran explicitamente su transporte simulado. Los procesos operativos
conservan `template` y el contrato real.

Los listeners 8000, 8001 y 4040 estaban libres, sin procesos Uvicorn/ngrok ni
unidades systemd del proyecto. Se iniciaron desde la raiz correcta:

- Backend PID `3195`, puerto 8000.
- Laboratorio PID `3200`, puerto 8001, modo Realtime con los overrides habituales
  `LAB_CALLS_ENABLED=true` y `LAB_AUDIO_MODE=realtime`.
- Ngrok PID `3212`, URL publica configurada en el proyecto.

Ambos Uvicorn tienen todos los valores administrados iguales al `.env` remoto,
incluido el token nuevo y el nombre/idioma aprobados.

| Comprobacion | Raspberry directa | Publica por ngrok |
| --- | --- | --- |
| `GET /` | 200, cuerpo esperado | 200, cuerpo esperado |
| `GET /webhook/whatsapp` | 200, challenge correcto | 200, challenge correcto |
| `POST /webhook/whatsapp`, evento vacio | 200, cuerpo esperado | 200, cuerpo esperado |

`GET /lab/health` devuelve 200, estado `ok`, audio `realtime`. La autenticacion de
solo lectura de Meta tambien devuelve 200.

## Prueba real y causa del bloqueo

Se intento una unica solicitud `send_template()` al doctor terminado en `3338`,
con los nueve ejemplos de `Paciente de prueba` aportados por el usuario. Fue una
prueba directa del cliente, sin crear citas, perfiles, eventos ni notificaciones
operativas falsas. Meta rechazo la solicitud antes de devolver un ID:

```text
probe_rejected={"http":404,"code":132001}
```

No se reenvio automaticamente ni se declaro entrega o recepcion. Las consultas
posteriores a Meta fueron de solo lectura:

- El token expone una cuenta de WhatsApp Business en sus scopes granulares.
- El recurso `phone_numbers` confirma que contiene el emisor configurado.
- Esa cuenta es **Test WhatsApp Business Account**, ID terminado en **5260**.
- La busqueda por `name=aviso_cita_medico` devuelve un catalogo vacio.
- El listado completo solo contiene `hello_world`, idioma `en_US`, estado `APPROVED`.

El resultado distingue el contrato aprobado reportado por el usuario de su
disponibilidad para este emisor. La entrega real y su callback `delivered`/`read`
permanecen pendientes.

## Identificacion de la cuenta desde la URL del usuario

El usuario proporciona la URL del administrador de plantillas. Sus parametros
indican el contexto de portafolio `business_id=2156006571926745` y el activo
seleccionado `asset_id=2157628355165252`. El segundo es candidato a WABA, no una
confirmacion de su tipo. Se realizaron consultas de solo lectura:

| Comprobacion | Resultado |
| --- | --- |
| WABA autorizado en scopes del token | `1047483564765260` (cuenta de pruebas) |
| Activo de la URL, candidato a WABA | `2157628355165252` |
| ID candidato incluido en targets del token inspeccionado | No |
| Consulta del ID candidato como cuenta | HTTP 400, `code=100`, `error_subcode=33` |
| Consulta de `phone_numbers` del candidato | HTTP 400, `100/33` |
| Consulta de `message_templates` del candidato | HTTP 400, `100/33` |

Se observaron identificadores diferentes, pero la URL no confirma por si sola el
tipo del activo. `100/33` puede indicar objeto inexistente, acceso insuficiente u
operacion incompatible; el error aislado no decide la causa ni prueba ausencia
de la plantilla. Los permisos de mensajeria/administracion tampoco sustituyen la
asignacion del activo al usuario o integracion que emite el token.

La conversacion adicional aportada por el usuario corrige las conclusiones
anteriores demasiado categoricas sobre `asset_id` y acceso. Se consolida el
procedimiento en [la memoria operativa](../whatsapp-meta-accounts.md): comparar la
misma cartera, comprobar asignacion y validar cuenta/numeros/plantilla por API.
`WHATSAPP_PHONE_NUMBER_ID` se obtiene del `id` del numero en `phone_numbers`,
despues de confirmar el emisor. No se modificaron emisor, destinatarios o
credenciales mediante una suposicion ni se repitio la solicitud rechazada.
