# Diseno - Motivo antes de crear una cita

## Estado

Implementado. La recoleccion ocurre en `ConversationService` antes de entregar la
creacion al `ToolExecutor`.

## Flujo implementado

```text
Mensaje del paciente con horario
    |
    v
LLM solicita create_appointment
    |
    v
ConversationService intercepta la mutacion
    |
    +-- guarda el horario en conversations.context_json
    +-- pregunta el motivo, sin tocar el calendario
    |
    v
Siguiente mensaje del paciente
    |
    v
ConversationService reconstruye create_appointment con el motivo recibido
    |
    v
ToolExecutor -> CalendarProvider
    |
    v
Respuesta al paciente y notificacion posterior al doctor
```

## Frontera de recoleccion

`AgentOrchestrator` ya permite ejecutar un manejador antes de cualquier mutacion.
`ConversationService` usa esa frontera para interceptar `create_appointment`, aunque
el LLM haya enviado un valor para `reason`. Ese valor se descarta porque no es una
prueba de que el paciente lo haya expresado.

`PendingAppointmentReason` conserva el `start_at`, el ID de la llamada, el mensaje
entrante que inicio la solicitud y los tiempos de creacion y expiracion. Vincular el
estado al mensaje evita crear la cita con el mismo texto si WhatsApp reintenta la
entrega de la pregunta. El estado se guarda bajo
`pending_appointment_reason` dentro de `conversations.context_json`, junto con
cualquier otro contexto existente.

## Resolucion

En el siguiente mensaje, `ConversationService` toma el texto entrante como motivo,
normaliza espacios y limpia el estado pendiente antes de ejecutar la llamada
reconstruida. La ejecucion usa el `PatientScope` resuelto por el backend. Si el
proveedor devuelve un error, se devuelve el error publico y no se emite un evento de
cita.

La respuesta de exito se construye con la cita creada y muestra fecha, hora y motivo.
No se muestra el ID interno. La respuesta se persiste antes de intentar la
notificacion al doctor, igual que en los demas eventos de agenda.

## Integracion con notificaciones

La pregunta inicial no ejecuta `ToolExecutor`, por lo que no genera
`AppointmentNotificationEvent`. El evento se emite unicamente desde la ejecucion
exitosa posterior al mensaje que contiene el motivo.
