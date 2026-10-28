# Diseno - Notificaciones al doctor

## Estado

Diseno implementado y verificado. La frontera de eventos, la persistencia de
entregas, la composicion, la entrega y la integracion del webhook estan
implementadas. La evidencia de ejecucion queda en
`docs/verification/2026-09-22-doctor-notifications-webhook.md`.

## Flujo implementado

Desde el 22 de octubre, `DoctorNotificationTrigger` centraliza la politica de
composicion, recuperacion del cuerpo preparado, entrega y aislamiento de errores.
El webhook lo invoca despues de persistir la respuesta al paciente. `VoiceTools`
usa el mismo `appointment_notification_event_from_result()` tras una mutacion
confirmada; guarda el evento junto al resultado antes de despertar al adaptador
`VoiceDoctorNotifications`. No se dispara por el texto que pronuncie el modelo.

El adaptador de voz solo recupera el nombre y el historial de la sesion/gestion,
los convierte en `DoctorNotificationContext` y llama al disparador compartido.
La tarea pertenece al lifespan de `/lab`, se despierta con cada mutacion y revisa
pendientes al arrancar y cada 60 s. Voz y texto del laboratorio reciben el mismo
adaptador y proveedor de agenda. No se abren tablas de pacientes operativos.

`voice_notification_events` conserva evento, nombre y limites de secuencia en la
misma transaccion que el resultado de la accion. Su identidad incluye sesion y
accion (`voice:<session_id>:<action_id>:<tool_name>`); las claves de chat conservan
su formato previo. Las entregas usan el mismo esquema y repositorio de
`doctor_notifications`, sin referencias a pacientes reales en la base exclusiva
del laboratorio. El aviso usa las transcripciones disponibles hasta ese limite;
una transcripcion ausente no se inventa ni bloquea la cita.
Iniciar explicitamente otra gestion actualiza `voice_sessions.notification_start_sequence`;
el evento congela el mayor limite entre ese inicio y el ultimo evento de la sesion.

El compositor y `appointment_messages.py` son los unicos responsables del cuerpo
para ambos canales. Un perfil sin numero vinculado muestra `No informado`. Se
congela el cuerpo al prepararlo; un fallo previo de resumen permite completar
el cuerpo antes de enviarlo. La preparacion del cuerpo y de todos sus destinatarios
ocurre en una transaccion `BEGIN IMMEDIATE`: solo se completan marcadores de
composicion fallida, sin sustituir otro cuerpo ya preparado. Solo quien reclama
una fila puede enviarla. Un cierre durante un envio, una respuesta perdida o un
fallo al persistir su resultado conserva `sending` para
conciliacion, sin un reenvio automatico potencialmente duplicado.
Un error de configuracion de doctores conserva el evento en su fuente con un log seguro,
sin impedir arrancar voz ni responder al paciente.

```text
Mensaje del paciente
    |
    v
ConversationService
    |
    v
AgentOrchestrator -> ToolExecutor -> CalendarProvider
                              |
                              +-- operacion de cita exitosa
                                      |
                                      v
                          AppointmentNotificationEvent
                                       |
                                       v
                           collector por solicitud
                                       |
                                       v
                           respuesta al paciente
                           enviada y persistida
                                       |
                                       v
                           DoctorNotificationTrigger
                               |
                               +-- SQLite: doctor_notifications
                               |
                               v
                     WhatsAppClient -> Doctores configurados
```

El evento de notificacion debe producirse a partir del resultado exitoso de la
herramienta, no a partir del texto final del LLM. `CalendarProvider` no debe
conocer al doctor ni enviar mensajes.

## Implementacion del corte 1

`notification_domain.py` define `AppointmentNotificationType`,
`AppointmentNotificationEvent` y el sink request-scoped para observar eventos.
`AgentOrchestrator` convierte los resultados exitosos de las tres mutaciones en
eventos y conserva el `tool_call_id`, el `incoming_message_id`, el `PatientScope`
y la cita resultante. `ConversationService.build_reply()` propaga el collector
junto con el ID del mensaje entrante.

Los resultados fallidos, las herramientas de solo lectura y los outputs que no
corresponden a la herramienta solicitada no emiten eventos. Este corte no persiste
ni envia notificaciones.

## Implementacion del corte 2

`persistence.py` crea `doctor_notifications` junto con restricciones para los tipos
de evento, estados, destinatario, cuerpo y contador de intentos. La restriccion
unica `(event_key, recipient_number)` conserva una sola entrega por destinatario
para cada mutacion.

`DoctorNotificationRepository` inserta entregas en `pending` sin reemplazar una
fila existente, salvo completar un cuerpo que aun no tuvo intentos tras un fallo
de resumen. Reclama de forma atomica filas `pending` o `failed` como `sending`,
registra los reintentos, conserva `last_error` y `provider_message_id`, y evita que
una fila `sent` vuelva a `failed` o se reclame otra vez. Las entregas de varios
destinatarios permanecen separadas aunque compartan `event_key`.

La bandeja queda preparada para el servicio de entrega, pero este corte no llama a
`WhatsAppClient` ni activa el flujo de notificaciones desde el webhook.

## Implementacion del corte 3

`notification_composer.py` separa la composicion de la entrega. `DoctorNotificationService`
carga desde SQLite el paciente y el historial persistido, y
`DoctorNotificationComposer` solicita un resumen estructurado al proveedor LLM.
La solicitud usa un prompt interno sin herramientas; `OpenAICompatibleLLMProvider`
expone `generate_text()` para no publicar los esquemas de agenda en esta llamada.

El contexto especifico del resumidor contiene el motivo expresado y el historial,
sin agregar fecha, horario, zona, estado o tipo de evento como datos estructurados.
El prompt pide sintetizar la charla (motivo, molestias, dudas y detalles relevantes)
y omitir los datos de agenda y la confirmacion aunque aparezcan en los mensajes.
Un motivo general se resume sin inventar sintomas.

El resultado se valida como resumen y senales de prioridad. Si el proveedor
devuelve una transcripcion, diagnosticos, recomendaciones clinicas o contenido
demasiado largo, se usa un resumen operativo seguro y se descartan las senales no
permitidas. Los valores internos del evento se eliminan antes de formar el cuerpo.

`render_doctor_notification()` produce el mismo formato para agendamiento,
modificacion y cancelacion. Incluye tipo de evento, fecha, hora, motivo, estado,
paciente, telefono, resumen y senales de prioridad. No
incluye IDs de SQLite, IDs de Google Calendar, IDs de herramientas ni credenciales.
El telefono del paciente se muestra con sus ultimos 10 digitos, sin el prefijo
internacional.
El nombre ausente se muestra como `No informado` sin inventar uno.
Los bloques de cita y paciente se delegan a `appointment_messages.py` despues del
saneamiento. El mismo renderizador produce la confirmacion al paciente con su
presentacion temporal; spec 020 y ADR 0053. El resumen y prioridad siguen siendo
contenido del doctor, compuesto despues de entregar la respuesta al paciente.

### Ampliacion - Prioridad semantica con evidencia (7 de octubre de 2026)

La llamada de resumen genera `summary`, `priority_signals` y
`priority_signal_evidence` (`{signal, quote}`). Comparte las instrucciones y el
catalogo de `appointment_reason_evaluation.py`, incluido `ocular_discharge`, con el
evaluador previo a crear la cita. El modelo interpreta significado y contexto; el
backend valida codigos y citas literales encontradas en el motivo o mensajes del
paciente, normalizando espacios, mayusculas y acentos. Las señales interpretadas no
se intersectan con las detectadas por expresiones regulares. Una respuesta sin
evidencia solo aporta el respaldo local, que se conserva aunque el modelo devuelva
una lista vacia. La evidencia no se renderiza como texto libre.

Antes de limitar a los ultimos mensajes, `DoctorNotificationService` separa el historial
con el ultimo evento anterior persistido de esa conversacion usando su `event_key`,
incluso si la entrega quedo pendiente o fallo. El compositor reconoce tambien las
respuestas fijas de exito enviadas por el backend como cierre de gestiones anteriores,
filtra por conversacion y excluye mensajes futuros. La respuesta del evento actual
permanece en el contexto del resumen. Los textos del asistente no son evidencia de
sintomas. El respaldo local procesa los mensajes entrantes en orden y despues el
motivo: una negacion posterior del mismo sintoma reemplaza la mencion anterior.

## Implementacion del corte 4

`notification_delivery.py` define `DoctorNotificationSettings` y carga la bandera
`DOCTOR_NOTIFICATIONS_ENABLED` junto con la lista
`DOCTOR_WHATSAPP_NUMBERS`. Cuando la bandera esta desactivada no se validan ni se
encolan destinatarios. Cuando esta activa, se exige al menos un numero E.164,
se recortan espacios, se normalizan prefijos aceptados y se eliminan duplicados.

`DoctorNotificationDeliveryService` crea o recupera una entrega pendiente por
`(event_key, recipient_number)`, reclama cada fila mediante
`DoctorNotificationRepository.claim_for_send()` y reutiliza
`WhatsAppClient.send_text()` con el cuerpo persistido. Un resultado exitoso marca la
fila como `sent` y conserva el ID devuelto por Meta cuando existe. Un error de
configuracion, timeout, conexion o HTTP se convierte en un mensaje estable y marca
solo esa fila como `failed`; el resto de destinatarios continua su intento.

Las filas `sent` no se vuelven a enviar. Las filas `failed` pueden reclamarse en un
intento posterior y conservan el contador de intentos.

## Implementacion del corte 5

`main.py` recolecta los eventos durante `ConversationService.build_reply()` y
ejecuta la composicion y entrega despues de enviar y persistir como `sent` la
respuesta al paciente. La configuracion, composicion, persistencia y envio de cada
notificacion se encapsulan para que un fallo al doctor no se propague al webhook;
`DoctorNotificationDeliveryService` conserva ademas el aislamiento entre
destinatarios.

## Frontera de eventos

El orquestador y el ejecutor necesitan exponer a la capa conversacional los
resultados exitosos de `create_appointment`, `reschedule_appointment` y
`cancel_appointment`. El mecanismo concreto queda sujeto al primer corte de
implementacion, pero debe cumplir estas reglas:

- El collector o callback debe pertenecer a una solicitud individual.
- No debe existir estado mutable global para relacionar eventos con pacientes.
- El evento debe incluir la operacion, el `PatientScope`, la cita resultante y una
  identidad estable de la ejecucion.
- Un resultado fallido no debe emitir un evento de notificacion exitoso.

La identidad de ejecucion debe permitir relacionar el evento con el mensaje
entrante y la llamada de herramienta. Esto es necesario para la idempotencia ante
reintentos del webhook.

## Mensaje a los doctores

`render_doctor_notification()` construye un unico cuerpo logico por evento con
este orden. La creacion de entregas por destinatario pertenece al corte de entrega:

1. Tipo de evento de la cita.
2. Datos de la cita.
3. Paciente y numero de telefono.
4. Resumen de la conversacion.
5. Senales de prioridad, si existen.

El nombre del paciente puede estar vacio en el modelo actual. En ese caso se debe
mostrar el numero de WhatsApp sin inventar un nombre.

El resumen se construye desde los mensajes persistidos y el motivo expresado
mediante el `LLMProvider` existente con un prompt interno separado, sin
tools y con reglas explicitas para no generar diagnosticos ni recomendaciones
clinicas. El cuerpo final queda listo para conservarse antes del envio, de modo que
un reintento no dependa de una nueva interpretacion del historial.

## Persistencia

La tabla `doctor_notifications` contiene como minimo:

- `id` interno.
- `event_key` del evento de agenda.
- `recipient_number` del doctor destinatario.
- `notification_type`.
- `patient_id`, `conversation_id` y `appointment_id` cuando correspondan.
- `body` del mensaje ya compuesto.
- `status`: `pending`, `sending`, `sent` o `failed`.
- `attempt_count` y `last_error`.
- `provider_message_id` cuando exista.
- `created_at`, `updated_at` y `sent_at`.

La persistencia funciona como una bandeja local de entregas. La unicidad se aplica
sobre `(event_key, recipient_number)`, porque un mismo evento genera una entrega
independiente para cada doctor. El repositorio permite encolar despues de confirmar
la operacion de agenda y antes de intentar el envio externo. La entrega puede
ejecutarse de forma sincrona en este MVP, pero el registro permite reintentos
posteriores sin introducir una cola distribuida.

## Entrega

En modo `text`, `DoctorNotificationDeliveryService` reutiliza `WhatsAppClient.send_text()` una vez por cada numero de
`DOCTOR_WHATSAPP_NUMBERS`. La variable contendra numeros separados por comas; el
backend debe recortar espacios, eliminar duplicados y validar que no quede ningun
destinatario vacio. Todos recibiran el mismo cuerpo logico del evento.

La respuesta al paciente usa el remitente entrante normalizado; el aviso interno
usa `recipient_number` de la entrega persistida para un doctor configurado. La
conversacion visible de WhatsApp depende del destinatario, no de `conversation_id`
de SQLite. Si el numero del paciente coincide con el de un doctor tras normalizar
el prefijo mexicano, ambos envios aparecen en la misma conversacion. Esto no
mezcla los cuerpos: el resumen y la prioridad solo se componen para el doctor.

La configuracion se habilitara mediante una bandera para mantener el comportamiento
actual por defecto.

El modo `template` usa `send_template()` con nombre, idioma y componentes del
mapeo explicito. Si falta alguno de esos datos conserva el aviso pendiente. No
se deben ocultar errores de configuracion ni marcar como enviada una notificacion
sin confirmacion del proveedor.

La prueba real del 22 de octubre confirmo `failed/131047` despues de un HTTP 200
con ID. El envio vigente usa texto libre y requiere un mensaje del doctor al bot
dentro de las ultimas 24 horas; el permiso no lo abre una llamada a `/lab`.
`doctor_notifications.status=sent` refleja actualmente aceptacion por la API.
En ese diagnostico, `receive_webhook()` reconocia sin persistir los eventos de
estado. El corte de callbacks incorpora la bandeja y proyeccion durables descritas
abajo; la instrumentacion temporal del diagnostico se retiro al terminar la captura.
La configuracion aprobada se adopta en `approved-template.md`; su prueba directa
de entrega real esta confirmada con callback `delivered` del 25/10/2026.

## Fallos y reintentos

### Corte de configuracion de plantilla

`DoctorNotificationSettings` incorpora `transport`, `template_name` y
`template_language`. `enabled` sigue indicando captura, no disponibilidad para
despachar. El cargador normaliza espacios y valida los destinatarios; el error de
transporte/plantilla se expone sin convertir una captura habilitada en deshabilitada.
El transporte omitido sigue siendo `text`; el ejemplo y la configuracion local
seleccionan `template`. Tras recibir el contrato aprobado se configuran nombre,
idioma y nueve parametros de cuerpo, documentados en `approved-template.md`.

`DoctorNotificationDeliveryService.blocked_reason` distingue datos incompletos,
datos invalidos y mapeo de plantilla pendiente. `record_deferred()` crea o
recupera las filas dentro de una transaccion inmediata, retiene las entregas
`pending`/`failed` y guarda el motivo sin aumentar `attempt_count`. Las filas
`sent` y `sending` permanecen intactas. `deliver()` aplica la misma puerta, por lo
que un consumidor directo tampoco puede caer en texto libre al seleccionar plantilla.

El disparador evalua la puerta antes de componer y usa un marcador de composicion
pendiente. El repositorio y el disparador distinguen ese marcador y el de fallo de
un cuerpo real; al recuperar el aviso, la composicion se completa antes del envio.
Un cuerpo ya preparado se conserva. Esto no requiere migrar SQLite: los eventos
ya estan en `reply_outbox.notification_events_json` y `voice_notification_events`.

`deliver_doctor_notifications()` devuelve si concluyeron todos los avisos. El
webhook solo marca `notifications_completed` cuando corresponde y su rama de
reintento carga el snapshot con `send_required=False`. El laboratorio usa su
evento pendiente y el contexto original en el ciclo compartido de 60 s. El corte
de recuperacion agrega ese ciclo al lifespan de chat.

La validacion local de nombre/idioma es solo sintactica. La validacion contra la
plantilla real aprobada se corresponde con `approved-template.md`. El envio
requiere tambien un mapeo explicito, no solo llenar dos variables.

### Corte de envio mediante plantilla

`notification_template.py` valida el arreglo de componentes configurado en
`DOCTOR_WHATSAPP_TEMPLATE_COMPONENTS`. Conserva el orden, los metadatos de botones
URL y los nombres opcionales de parametros. Las referencias simples a los datos
del aviso permiten agrupar varios campos sin asumir la cantidad de variables.
Se exige cubrir todos los campos actuales o el cuerpo completo. La resolucion
trabaja sobre una copia del JSON y no interpreta instrucciones del paciente.

`appointment_message_fields()` comparte los valores de presentacion con el
renderizador. El compositor expone `template_data` a partir de esos valores
saneados, resumen y señales, sin parsear el mensaje renderizado. El disparador
entrega cuerpo y datos al mismo servicio tanto en chat como en laboratorio.

Las migraciones compartidas agregan `template_data_json` y `template_payload_json`
opcionales a `doctor_notifications` en ambas bases. El repositorio congela datos
y cuerpo conjuntamente; al reclamar una entrega conserva nombre, idioma y
componentes con `COALESCE`, evitando reemplazarlos en un reintento. El payload
persistido determina el envio de los intentos posteriores. Los registros antiguos
permanecen validos con snapshots nulos; solo su cuerpo completo esta disponible
como respaldo explicito, sin recomponer datos que podrian pertenecer a otra gestion.

`WhatsAppClient` comparte `_send()` para texto y plantilla, manteniendo la misma
version de Cloud API y autenticacion. Los errores de mapeo o campos ausentes se
retienen antes de reclamar intentos. Los errores HTTP conocidos quedan fallidos;
respuestas perdidas o sin ID de Meta quedan inciertas sin reenvio automatico.

La plantilla real se configura como `aviso_cita_medico`, `es_MX`, con nueve
parametros posicionales de cuerpo. El encabezado y la linea final son fijos de
Meta. Se conserva el adaptador generico y los layouts ficticios en sus pruebas;
una prueba adicional valida el contrato real y sus ejemplos completos con HTTP
simulado. La aceptacion y entrega reales requieren la comprobacion del proveedor.

### Corte de recuperacion y espera durable

`NotificationRecoveryWorker` comparte ciclo, cierre y exclusiones entre
`ChatDoctorNotifications` y `VoiceDoctorNotifications`. El adaptador de chat lee
respuestas `sent` con eventos incompletos, incluida una fuente antigua completada
que conserve una entrega pendiente sin snapshot. Nunca llama al servicio
conversacional ni a herramientas. El laboratorio adapta los eventos ya guardados.
Despues de cada fuente se recuperan tambien las entregas con su propio `event_json`.
El chat refresca el disparador desde el entorno efectivo; la recarga habitual
aplica cambios de `.env` en ambos procesos.

El disparador registra primero las entregas y un contexto acotado. El repositorio
usa snapshots de solo escritura inicial; una composicion posterior utiliza el
contexto ganador de esa transaccion, no un perfil actualizado. Los destinatarios
quedan fijados al primer registro, y las entregas a doctores retirados se detienen.

La puerta de elegibilidad se aplica antes de componer y en la reclamacion SQL.
`next_attempt_at` impide saltarse la espera desde otro worker o un webhook. La
politica comun distingue fallos transitorios, rechazos de configuracion y
resultados inciertos. El tiempo de espera y la clasificacion se conservan tras
reiniciar. Una huella por destinatario identifica cambios relevantes de transporte,
plantilla y credenciales sin guardarlas literalmente ni mostrarlas en los logs.

La reclamacion guarda un registro de `doctor_notification_attempts` en la misma
transaccion: numero de intento, cuerpo, payload y revision local. Las finalizaciones
comparan el numero de intento para evitar que una respuesta tardia sobreescriba
un resultado conciliado. El payload solo puede cambiar tras un rechazo conocido
de configuracion y su correccion; los intentos anteriores siguen auditados.

`reconcile_doctor_notification.py` opera sobre un aviso y numero de intento
verificados. Registra evidencia de aceptacion o ausencia de entrega y permite
liberar una correccion externa de configuracion. No consulta ni muta la agenda,
ni envia por si misma. Un `sending` no tiene vencimiento automatico. Los
callbacks de Meta usan esta auditoria en el corte siguiente.

### Corte de callbacks durables

`notification_statuses.py` extrae y normaliza los estados y almacena su identidad
canonica en `whatsapp_delivery_receipts`, exclusivamente en la base de chat.
El webhook confirma esa escritura en un thread antes de devolver 200 y agrega
una proyeccion de fondo. Si falla la escritura retorna 503, sin volcar valores
del proveedor al error. Un worker del lifespan repite pendientes cada 5 s y al
arrancar, incluso si el envio de avisos esta deshabilitado.

La proyeccion busca primero intentos por ID y destinatario; puede usar el ID del
registro historico si aun no tenia auditoria. Se liga durablemente el recibo al
canal/aviso/intento antes de actualizar el destino. Cada destino usa una transaccion
inmediata e idempotente; el inbox se marca despues. No se necesita una transaccion
distribuida entre las dos SQLite. Si se interrumpe entre ambas escrituras, el
recibo se reaplica sin duplicar la programacion del fallo.

`delivery_status`, `delivery_status_at`, `delivery_error_codes_json` y
`api_accepted_at` se agregan tanto al aviso como al intento. La evidencia se reduce
por progreso (`read`/`delivered` sobre `failed`, y `failed` sobre `sent`) y timestamp
del mismo nivel. La proyeccion mantiene el resultado mas fuerte ya observado para
resolver escritores concurrentes. El snapshot de eventos se marca individualmente
por clave, evitando confirmar un callback que llego durante otra proyeccion.

El intento conserva la huella de configuracion al reclamarlo. Un fallo asincrono
del intento actual aplica la politica de espera/bloqueo sin borrar ID ni aceptacion.
Los callbacks tardios de intentos anteriores solo actualizan su historial. Una
confirmacion de entrega/lectura del intento actual cancela reintentos; un nuevo
HTTP aceptado no borra el contador de fallos de entrega aun pendientes.

Los callbacks desconocidos no crean avisos, pacientes o intentos. Los asociados a
respuestas al paciente se marcan como tales. La proyeccion a voz y la utilidad de
conciliacion usan conexiones a la base existente, sin introducir tablas de pacientes
ni arrancar un `VoiceRepository` con efectos de recuperacion de sesiones.

### Resultado de los intentos

- Un fallo de composicion o persistencia no afecta al paciente y no propaga la
  excepcion al webhook.
- Un fallo de WhatsApp deja la entrega de ese destinatario en `failed` con el error
  normalizado.
- Un envio exitoso cambia la entrega a `sent` y conserva el ID del proveedor.
- Una entrega `sent` nunca se vuelve a enviar por un webhook duplicado.
- El fallo de una entrega no cancela ni oculta las entregas dirigidas a otros
  destinatarios.
- Una entrega `failed` queda disponible segun su espera o tras corregir el bloqueo;
  los ciclos de recuperacion son locales al lifespan, sin un worker distribuido.

## Privacidad

Cada doctor recibira solo la informacion necesaria para entender la cita y
continuar la atencion. El mensaje no debe incluir secretos, identificadores
internos, transcripciones completas ni afirmaciones diagnosticas. El resumen debe
mantener las senales de prioridad como indicadores internos, no como diagnosticos.
