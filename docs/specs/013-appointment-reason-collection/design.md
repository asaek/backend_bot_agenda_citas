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
    +-- pregunta el nombre en cada cita y actualiza patients.name con la respuesta
    +-- pregunta el motivo, sin tocar el calendario
    |
    v
Siguiente mensaje del paciente
    |
    v
Validador local de calidad minima
    |
    +-- texto ilegible o ambiguo --> conserva la solicitud y pide aclaracion
    |
    +-- texto aceptable --> evaluacion estructurada
                              |
                              +-- needs_clarification/out_of_scope --> conserva estado
                              |
                              +-- valid --> registra metadata y reconstruye create_appointment
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

`PendingAppointmentReason` conserva el `start_at`, el ID de la llamada, los mensajes
entrantes que iniciaron la solicitud y entregaron el nombre, si la solicitud requiere
capturar el nombre, y los tiempos de creacion y expiracion. El indicador permite que
las solicitudes pendientes creadas antes de esta regla mantengan su comportamiento
anterior. Vincular el estado a esos mensajes evita crear la cita con el mismo texto si
WhatsApp reintenta la entrega de una pregunta. El estado se guarda bajo
`pending_appointment_reason` dentro de `conversations.context_json`, junto con
cualquier otro contexto existente. Tambien conserva `attempt_count` y
`last_evaluation` mientras espera una respuesta.

## Resolucion

Antes de tomar el siguiente mensaje como nombre o motivo, `ConversationService` consulta
el router de `specs/016-conversation-intent-routing/`. Una peticion nueva explicita
limpia la solicitud de creacion pendiente y se atiende sin ejecutar `create_appointment`;
una pregunta ambigua se aclara en vez de convertirla en nombre o motivo.

En cada cita nueva, aunque el paciente ya tenga un nombre registrado,
`ConversationService` toma el siguiente mensaje, normaliza espacios, lo valida como
nombre y lo guarda o actualiza en `patients.name` junto con el marcador del mensaje
que lo entrego. El reintento de ese mensaje solo devuelve la pregunta por el motivo.
Despues, `ConversationService` toma el siguiente mensaje como motivo, lo pasa por
`appointment_reason_validation.py` y normaliza espacios sin reemplazar el contenido
del paciente. Si el texto es evidentemente ilegible, devuelve una solicitud de
aclaracion y conserva el estado pendiente, por lo que no toca el calendario ni emite
una notificacion.

Para texto legible, `StructuredAppointmentReasonEvaluator` solicita un unico objeto
JSON al proveedor LLM. El backend valida enums, confianza y señales permitidas; una
respuesta invalida se degrada a `needs_clarification`. El LLM solo clasifica y nunca
proporciona el `reason`. Las señales detectadas localmente se combinan con las
señales permitidas del LLM, sin aceptar diagnosticos ni texto libre. Los codigos se
convierten mediante un catalogo compartido en mensajes operativos, por ejemplo
`El paciente refiere dolor ocular que podria requerir atencion prioritaria.`

El codigo `eye_redness` se detecta localmente a partir de expresiones como `ojos rojos`
en el motivo actual de la cita y usa el mensaje operativo `El paciente refiere ojos rojos
que podrían requerir atención prioritaria.`. El compositor deriva las señales del motivo
de `event.appointment`, no de todo el historial; solo conserva codigos o mensajes del
catalogo respaldados por ese motivo y descarta texto libre producido por el modelo,
incluidos estados como `cita confirmada`.

Cada intento actualiza el estado pendiente antes de responder. Un resultado
`needs_clarification` o `out_of_scope` lo conserva. Un resultado `valid` con
confianza minima registra `last_appointment_reason_evaluation`, limpia el estado
pendiente y ejecuta la llamada reconstruida con el texto normalizado del paciente.
La politica del MVP permite continuar aun con señales de prioridad, que quedan
registradas y pueden incluirse en la notificacion interna posterior. La ejecucion usa el `PatientScope`
resuelto por el backend. Si el proveedor devuelve un error, se devuelve el error
publico y no se emite un evento de cita.

El validador aplica solamente reglas de calidad minima: no usa una lista cerrada de
sintomas y no exige un diagnostico. La evaluacion usa categorias operativas, no
clasificacion clinica. Las señales de prioridad son indicadores internos, se
describen sin nombres de enfermedades y no representan diagnosticos ni instrucciones
de atencion. Antes de usar el sistema con pacientes reales, una politica clinica
debe definir como se revisan y atienden.

La respuesta de exito se construye con la cita creada y muestra fecha, hora y motivo.
No se muestra el ID interno. La respuesta se persiste antes de intentar la
notificacion al doctor, igual que en los demas eventos de agenda.

## Integracion con notificaciones

La pregunta inicial no ejecuta `ToolExecutor`, por lo que no genera
`AppointmentNotificationEvent`. El evento se emite unicamente desde la ejecucion
exitosa posterior al mensaje que contiene el motivo.
