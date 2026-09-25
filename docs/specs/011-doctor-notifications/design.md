# Diseno - Notificaciones al doctor

## Estado

Diseno implementado y verificado. La frontera de eventos, la persistencia de
entregas, la composicion, la entrega y la integracion del webhook estan
implementadas. La evidencia de ejecucion queda en
`docs/verification/2026-09-22-doctor-notifications-webhook.md`.

## Flujo implementado

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
                           DoctorNotificationService
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
fila existente, reclama de forma atomica filas `pending` o `failed` como `sending`,
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

El resumen se construye desde los mensajes persistidos y la informacion operativa
de la cita mediante el `LLMProvider` existente con un prompt interno separado, sin
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

`DoctorNotificationDeliveryService` reutiliza `WhatsAppClient.send_text()` una vez por cada numero de
`DOCTOR_WHATSAPP_NUMBERS`. La variable contendra numeros separados por comas; el
backend debe recortar espacios, eliminar duplicados y validar que no quede ningun
destinatario vacio. Todos recibiran el mismo cuerpo logico del evento.

La configuracion se habilitara mediante una bandera para mantener el comportamiento
actual por defecto.

Si la politica de Meta exige una plantilla para iniciar una conversacion fuera de
la ventana permitida, se agregara un metodo de plantillas en un corte separado. No
se deben ocultar errores de configuracion ni marcar como enviada una notificacion
sin confirmacion del proveedor.

## Fallos y reintentos

- Un fallo de composicion o persistencia no afecta al paciente y no propaga la
  excepcion al webhook.
- Un fallo de WhatsApp deja la entrega de ese destinatario en `failed` con el error
  normalizado.
- Un envio exitoso cambia la entrega a `sent` y conserva el ID del proveedor.
- Una entrega `sent` nunca se vuelve a enviar por un webhook duplicado.
- El fallo de una entrega no cancela ni oculta las entregas dirigidas a otros
  destinatarios.
- Una entrega `failed` queda disponible para una llamada posterior del servicio sin
  introducir un worker distribuido.

## Privacidad

Cada doctor recibira solo la informacion necesaria para entender la cita y
continuar la atencion. El mensaje no debe incluir secretos, identificadores
internos, transcripciones completas ni afirmaciones diagnosticas. El resumen debe
mantener las senales de prioridad como indicadores internos, no como diagnosticos.
