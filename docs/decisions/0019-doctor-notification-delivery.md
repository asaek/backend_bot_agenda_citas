# ADR 0019 - Entrega de notificaciones al doctor

## Estado

Aceptada, implementada y verificada. Los cortes de eventos, persistencia,
composicion, entrega e integracion del webhook estan implementados; la evidencia de
ejecucion queda en `docs/verification/2026-09-22-doctor-notifications-webhook.md`.

## Contexto

El chatbot ya puede modificar citas mediante el `ToolExecutor` y enviar mensajes
de texto mediante WhatsApp Cloud API. Uno o varios doctores necesitan recibir un
mensaje por cada cita agendada, modificada o cancelada, con un resumen de la
conversacion. La entrega no debe duplicarse ni convertir en fallida la respuesta
del paciente si la API externa no esta disponible.

## Decision

Reutilizar WhatsApp Cloud API y `WhatsAppClient` como canal inicial. El backend
recibira una lista de numeros en `DOCTOR_WHATSAPP_NUMBERS` y cada evento exitoso de
agenda se convertira en una entrega persistida en SQLite para cada numero antes del
envio. La clave de idempotencia sera la pareja `(event_key, recipient_number)` y
cada entrega tendra su propio estado y registro de error. El cuerpo final incluira
el evento de la cita y el resumen conversacional, y sera igual para todos los
destinatarios configurados.

Los envios se mantendran fuera de `CalendarProvider`. Un fallo para un destinatario
quedara registrado sin impedir los intentos dirigidos a los demas y no afectara la
operacion de agenda ni la respuesta al paciente. No se introducira una cola
distribuida durante este MVP.

La implementacion incremental usa `doctor_notifications` como bandeja local. La
pareja `(event_key, recipient_number)` es unica, y el repositorio reclama de forma
atomica entregas `pending` o `failed` antes de un envio futuro. Los estados, errores,
intentos y `provider_message_id` quedan en SQLite; una entrega `sent` no se vuelve a
intentar por un webhook duplicado.

## Ampliacion adoptada - Texto y voz (22 de octubre de 2026)

Se adopta `DoctorNotificationTrigger` como entrada comun de composicion y entrega.
Chat y `VoiceTools` convierten resultados exitosos con la misma funcion de dominio;
el canal adapta el contexto, sin duplicar plantilla, resumen, prioridad ni reglas
de destinatarios. El chat conserva su momento de entrega posterior a la respuesta.

El laboratorio guarda el evento junto al resultado de la accion en su propia
SQLite y lo entrega desde una tarea del lifespan, con reintentos cada 60 s y al
arrancar. Se comparte el esquema/repositorio de entregas, omitiendo solo las claves
foraneas a pacientes operativos en la base de voz. Esto preserva el aislamiento y
evita insertar identidades ficticias en la base de pacientes para reutilizar avisos.

El cuerpo preparado se reutiliza ante fallos de WhatsApp; un resumen fallido se
recompone antes del primer envio. Una entrega reclamada no puede enviarse desde
otro intento; `sending` incierto requiere conciliacion. No se agregan servicios ni
colas distribuidas. El nombre y los limites de historial se conservan por evento;
un perfil sin numero vinculado se presenta como `Telefono: No informado`.

La integracion no acredita entrega real mientras el token de Meta este vencido,
ni completa Calling o continuidad con identidades operativas de la especificacion 021.

### Limite operativo confirmado el 22 de octubre

Con credenciales validas se observo HTTP 200 seguido de `failed/131047`: el
doctor no habia escrito al bot en las ultimas 24 horas. La implementacion actual
envia texto libre; para avisos fuera de esa ventana requiere una plantilla
aprobada, todavia pendiente. Abrir una llamada en laboratorio no abre la ventana
de mensajeria del destinatario. `sent` local solo refleja aceptacion de la API;
los estados asincronos aun no se persisten. La evidencia de la ventana queda en
`docs/verification/2026-10-22-whatsapp-doctor-delivery-window.md`.

## Ampliacion adoptada - Captura con plantilla pendiente (22 de octubre de 2026)

Separar la bandera de captura de la disponibilidad del transporte. Se agregan
`DOCTOR_NOTIFICATION_TRANSPORT`, `DOCTOR_WHATSAPP_TEMPLATE_NAME` y
`DOCTOR_WHATSAPP_TEMPLATE_LANGUAGE`. El transporte ausente mantiene `text` por
compatibilidad; el ejemplo selecciona `template` y deja nombre e idioma vacios.

Se reutilizan las bandejas SQLite existentes. El disparador conserva una entrega
por doctor con estado `pending` y motivo de configuracion antes de resumir o
reclamar un envio. El chat mantiene sin completar el evento en `reply_outbox`;
el laboratorio conserva su evento en el ciclo de recuperacion existente. Los
estados `sent` y `sending` no retroceden al retener un aviso.

Se evita equiparar una plantilla incompleta con avisos deshabilitados, porque eso
descartaria eventos de citas ya realizadas. La disponibilidad se consulta tanto
en el disparador como en el entregador, evitando texto libre como respaldo
accidental. La validacion de nombre/idioma solo comprueba formato. El corte
posterior de envio se registra a continuacion; aprobacion/componentes reales y
callbacks siguen pendientes.

## Ampliacion adoptada - Adaptador y mapeo explicito (22 de octubre de 2026)

Implementar `send_template()` en el mismo cliente HTTP y seleccionar ese transporte
desde el entregador comun. El mapeo se configura como JSON de componentes, con
referencias a los datos saneados del compositor; permite agrupar campos y conservar
orden/nombres sin decidir de antemano cuantas variables tendra la plantilla.
El mapeo exige preservar los datos actuales o el cuerpo completo del aviso.

Persistir los campos estructurados junto al cuerpo evita extraerlos de texto libre
o volver a resumir en los reintentos. Nombre, idioma y componentes se congelan al
reclamar el primer intento por destinatario y se reutilizan despues de reiniciar.
Se agregan dos columnas opcionales mediante una migracion comun a ambas bases,
conservando los avisos historicos. Un cuerpo antiguo solo se puede usar completo,
sin inventar sus campos. Los errores de mapeo conservan el aviso pendiente.

La implementacion cubre parametros de texto en cuerpo, encabezado y botones URL;
otros componentes esperan un contrato explicito. Nombre, idioma y mapeo reales
siguen vacios y no se declara aprobada una plantilla por llenar la configuracion.
Un HTTP exitoso sin ID de Meta mantiene resultado incierto; los callbacks de
entrega siguen pendientes.

## Ampliacion adoptada - Recuperacion local y conciliacion (22 de octubre de 2026)

Compartir un ciclo de lifespan entre chat y laboratorio para recuperar solamente
eventos persistidos. La bandeja por destinatario guarda evento y contexto acotado;
las fuentes existentes cubren la interrupcion previa a capturar la entrega. La
recuperacion no llama herramientas ni reconstruye avisos desde el estado de agenda.
Los destinatarios de un evento quedan fijados al primer registro.

Persistir fechas de proximo intento y clasificacion, con espera exponencial de
60 s a 3600 s y respeto de `Retry-After` hasta 24 h. Los rechazos de configuracion
esperan una correccion relevante o una liberacion explicita tras corregir Meta.
Los resultados inciertos nunca se liberan por un timeout de la reclamacion.

Auditar cada despacho en `doctor_notification_attempts`, incluyendo revision local,
payload y resultado. Los intentos transitorios conservan el payload; una
configuracion rechazada puede corregirse manteniendo el intento anterior. Una
conciliacion versionada y respaldada por evidencia resuelve aceptacion o ausencia
de entrega. Una respuesta tardia no reemplaza esa resolucion. Esto conserva la
posibilidad de integrar callbacks despues sin asumir que un HTTP 200 es entrega.

## Ampliacion adoptada - Callbacks durables de entrega (22 de octubre de 2026)

Separar aceptacion de la API de evidencia de envio/entrega/lectura/fallo. Guardar
los callbacks en un inbox de la SQLite de chat antes del ACK y proyectarlos en
chat o voz por ID y destinatario. El historial de intentos conserva esos estados;
una respuesta HTTP no se presenta como confirmacion de entrega.

La proyeccion por destino y el ACK individual de eventos son idempotentes. Se
prefiere conservar pendientes antes que adivinar el canal o el ID. El ciclo de
lifespan cada 5 s resuelve carreras con el guardado tardio del ID sin introducir
un servicio externo o una transaccion distribuida. La lectura/entrega comprobada
prevalece sobre fallos y estados de envio atrasados; se conserva todo el historial.

Un fallo asincrono alimenta una sola vez el control de reintentos del intento actual
con su huella de configuracion. Las respuestas de intentos antiguos no reprograman
el nuevo. Los historicos solo se migran como aceptados cuando ya tienen ID, sin
fabricar evidencia. Las conexiones a voz y la conciliacion preservan su esquema.

## Alternativas consideradas originalmente

- Enviar directamente desde `CalendarProvider`: se rechaza porque mezcla agenda y
  comunicacion y dificulta las pruebas.
- Mantener notificaciones solo en memoria: se rechaza porque se perderian ante un
  reinicio y no permitiria idempotencia.
- Introducir Redis o un worker desde el primer corte: se pospone porque el MVP
  actual usa una sola instalacion SQLite y no necesita procesamiento distribuido.

## Consecuencias

- Se reutiliza la autenticacion y el cliente de WhatsApp existentes.
- SQLite conserva una auditoria local y permite reintentos posteriores.
- El primer intento puede ejecutarse desde el webhook; los ciclos locales recuperan
  pendientes sin requerir otro mensaje del paciente ni agregar servicios externos.
- Los numeros y las credenciales de los doctores permanecen fuera del codigo.
