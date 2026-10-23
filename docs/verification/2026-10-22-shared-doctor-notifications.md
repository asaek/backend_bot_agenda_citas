# Disparador compartido de notificaciones al doctor — 22/10/2026

## Diagnostico y alcance

La reproduccion en la Raspberry confirmo las tres mutaciones de voz con cero
intentos de aviso al doctor. `VoiceTools` ejecutaba la herramienta directamente,
sin convertir el resultado en un evento ni llamar al servicio de notificaciones.
La autenticacion Meta, comprobada por GET de solo lectura, devolvio 401 y
190/463 (token vencido). Los avisos estaban habilitados con un destinatario.

## Implementacion

- `DoctorNotificationTrigger` comparte composicion, cuerpo preparado, entrega y
  aislamiento de fallos entre chat y laboratorio. No hay una plantilla de voz.
- Ambas entradas usan `appointment_notification_event_from_result` para convertir
  solamente resultados tipados exitosos de crear, reprogramar y cancelar.
- `VoiceRepository.save_action_result` conserva resultado y evento atomicamente.
  El evento contiene identidad de sesion/accion, nombre y limites de historial;
  la tarea del lifespan usa las transcripciones disponibles de esa gestion.
- La tarea recupera pendientes al arrancar, al confirmar otra mutacion y cada 60 s.
  Un reintento no invoca herramientas de agenda y conserva el cuerpo preparado.
- Los fallos de resumen se recomponen antes del envio. La reclamacion atomica impide
  que dos intentos envien la misma fila concurrentemente. `sending` incierto queda
  para conciliacion y no se reenvia automaticamente.
- La revision detecto y corrigio la posible repeticion tras una respuesta Meta
  perdida, el reemplazo concurrente del cuerpo de otro destinatario y la herencia
  de sintomas al iniciar explicitamente una gestion nueva. Cada caso tuvo una
  regresion fallida antes de su correccion. Los codecs de eventos tambien se unificaron.
- La configuracion invalida de doctores no impide arrancar el laboratorio;
  deshabilita los avisos y deja un error seguro.
- El laboratorio conserva su SQLite e identidad ficticia; reutiliza el esquema de
  entrega sin insertar pacientes operativos. El telefono se muestra no informado.
- No se migran ni notifican retroactivamente acciones previas sin evento de aviso.

## Pruebas en Raspberry Pi

Las pruebas usan SQLite temporal, agenda fake, proveedor de resumen falso y cliente
WhatsApp de registro; no escriben citas Google ni envian mensajes reales.

La prueba inicial fallo por ausencia de `notification_trigger`. La siguiente
regresion detecto que un fallo de resumen podia terminar entregando su marcador de
error; despues de corregirlo, el reinicio y reintento entregan el cuerpo completo.
Una regresion concurrente tambien fallo primero con dos envios; despues de corregir
la reclamacion, un unico intento envia la fila.

```text
DOCTOR_NOTIFICATIONS_ENABLED=false PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  -m unittest discover -s tests -p test_voice_notifications.py -v
Ran 9 tests
OK
```

Cubren propuesta sin envio, creacion, reprogramacion y cancelacion automaticas desde
`VoiceSession`, nombre/formato/resumen, duplicado de herramienta, rechazo, fallo de
agenda, fallo de resumen, fallo de WhatsApp, reinicio, recuperacion desde la factory,
respuesta Meta perdida e inicio de una gestion sin sintomas heredados. Una prueba
de entrega concurrente comprueba un solo cuerpo para todos los doctores; otra de
factory comprueba que una configuracion invalida no bloquea voz. La frontera de
gestion se deriva de la ultima entrada del paciente: una salida o placeholder
posterior del asistente no elimina los sintomas de la solicitud nueva.

Una ejecucion focalizada previa de notificaciones, voz, laboratorio y webhook
completo paso 142 pruebas. La suite completa final, despues de las correcciones de
revision, se ejecuto desde la raiz del mirror mediante `unittest` discovery:

```text
DOCTOR_NOTIFICATIONS_ENABLED=false PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  -m unittest discover -s tests -q
Ran 500 tests in 72.970s
OK
```

## Revision final

### Standards

Sin hallazgos pendientes. Se corrigieron el reemplazo concurrente de cuerpos y la
duplicacion de codecs de evento. La revision se hizo sobre una copia del trabajo
en un worktree separado; no ejecuto pruebas ni modifico el codigo.

### Spec

Sin hallazgos pendientes. Se corrigieron el reenvio tras respuesta Meta perdida y
los limites de contexto al comenzar otra gestion, incluida la presencia de un
placeholder del asistente posterior al mensaje del paciente. Las regresiones
fallaron antes de corregir cada caso y estan en la suite final.

Resumen: 0 hallazgos abiertos de estandares y 0 de requisitos.

## Sincronizacion y runtime

Se sincronizaron solo los archivos de la funcionalidad y su SDD desde el checkout
local; se revisaron las previsualizaciones de rsync. Se conservo el `.env` existente
de la Pi (modo `600`); ambos procesos nuevos coinciden con sus valores efectivos.

No se encontraron unidades systemd de proyecto ni sesiones de llamada/texto
activas. Se verificaron puerto, argumentos y directorio antes de detener cada PID.

| Proceso | PID anterior | PID nuevo | Resultado |
| --- | ---: | ---: | --- |
| Backend de texto, 8000 | 759310 | 3842630 | Salud 200 y configuracion coincidente |
| Laboratorio Realtime, 8001 | 2149568 | 3842688 | Salud 200, Realtime y Google |

La SQLite de voz migro el limite de gestion y las tablas de avisos. Al arrancar
habia cero eventos/entregas de voz: no se enviaron avisos retroactivos. El proceso
ngrok existente se conservo. Se abrio el forwarding SSH local 8001 y se comprobo
`http://localhost:8001/lab`, sin iniciar llamada ni consumir Realtime.

| Comprobacion posterior | Resultado |
| --- | --- |
| Salud de texto local/publica | 200, cuerpo esperado |
| Webhook GET local/publico | 200, challenge correcto |
| Webhook POST vacio local/publico | 200, cuerpo esperado |
| `/lab/health` y `/lab` desde Pi y Mac | 200, Realtime y Google |
| Configuracion de avisos | Habilitada, un destinatario |
| Graph API GET de solo lectura, `fields=id` | 401, OAuthException 190/463 |

## Estado de cierre

Implementacion compartida, SDD, pruebas, revision, sincronizacion y recarga
completas. La entrega real sigue bloqueada por el token de Meta vencido (190/463).
Es necesario renovarlo para que los avisos puedan llegar al telefono; las pruebas
con dobles no acreditan recepcion real. No se imprimieron credenciales, enviaron
mensajes reales ni modificaron citas Google durante esta verificacion.
