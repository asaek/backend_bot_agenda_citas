# Diseno - Notificaciones al doctor

## Estado

Borrador de diseno tecnico. La implementacion todavia no ha comenzado.

## Flujo propuesto

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
                          DoctorNotificationService
                              |
                              +-- SQLite: doctor_notifications
                              |
                              v
                          WhatsAppClient -> Doctor
```

El evento de notificacion debe producirse a partir del resultado exitoso de la
herramienta, no a partir del texto final del LLM. `CalendarProvider` no debe
conocer al doctor ni enviar mensajes.

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

## Mensaje al doctor

`DoctorNotificationService` debe construir un unico cuerpo por evento con este
orden:

1. Tipo de evento de la cita.
2. Datos de la cita.
3. Paciente y numero de telefono.
4. Resumen de la conversacion.
5. Senales de prioridad, si existen.

El nombre del paciente puede estar vacio en el modelo actual. En ese caso se debe
mostrar el numero de WhatsApp sin inventar un nombre.

El resumen se construira desde los mensajes persistidos y la informacion de la
cita. Puede usar el `LLMProvider` existente con un prompt interno separado, sin
tools y con reglas explicitas para no generar diagnosticos ni recomendaciones
clinicas. El cuerpo final debe conservarse antes del envio para que un reintento no
dependa de una nueva interpretacion del historial.

## Persistencia propuesta

Se propone una tabla `doctor_notifications` con, como minimo:

- `id` interno.
- `event_key` unica para idempotencia.
- `notification_type`.
- `patient_id`, `conversation_id` y `appointment_id` cuando correspondan.
- `body` del mensaje ya compuesto.
- `status`: `pending`, `sending`, `sent` o `failed`.
- `attempt_count` y `last_error`.
- `provider_message_id` cuando exista.
- `created_at`, `updated_at` y `sent_at`.

La persistencia funciona como una bandeja local de entrega. El mensaje se encola
despues de confirmar la operacion de agenda y antes de intentar el envio externo.
La entrega puede ejecutarse de forma sincrona en este MVP, pero el registro debe
permitir reintentos posteriores sin introducir una cola distribuida.

## Entrega

Se reutilizara `WhatsAppClient.send_text()` con `DOCTOR_WHATSAPP_NUMBER` como
destinatario. La configuracion se habilitara mediante una bandera para mantener el
comportamiento actual por defecto.

Si la politica de Meta exige una plantilla para iniciar una conversacion fuera de
la ventana permitida, se agregara un metodo de plantillas en un corte separado. No
se deben ocultar errores de configuracion ni marcar como enviada una notificacion
sin confirmacion del proveedor.

## Fallos y reintentos

- Un fallo de composicion deja la notificacion en `failed` y no afecta al paciente.
- Un fallo de WhatsApp deja la notificacion en `failed` con el error normalizado.
- Un envio exitoso cambia el estado a `sent` y conserva el ID del proveedor.
- Una notificacion `sent` nunca se vuelve a enviar por un webhook duplicado.
- La politica concreta para reintentar notificaciones fallidas se implementara sin
  un worker distribuido en este corte.

## Privacidad

El doctor recibira solo la informacion necesaria para entender la cita y continuar
la atencion. El mensaje no debe incluir secretos, identificadores internos,
transcripciones completas ni afirmaciones diagnosticas. El resumen debe mantener
las senales de prioridad como indicadores internos, no como diagnosticos.
