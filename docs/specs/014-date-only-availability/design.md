# Diseno - Horarios libres antes de elegir una cita

## Estado

Implementado.

## Flujo

```text
Mensaje con intencion de agendar y dia sin hora
    |
    v
ConversationService detecta el rango del dia
    |
    v
ToolExecutor -> check_availability
    |
    v
Respuesta con slots unicos
    |
    v
El paciente elige una hora
    |
    v
ConversationService valida la seleccion contra el estado persistido
    |
    +-- hora no ofrecida --> conserva slots y pide otra seleccion
    |
    +-- hora valida --> guarda pending_appointment_reason
                          |
                          +-- backend pregunta nombre/motivo sin LLM
                          v
                    flujo normal de creacion controlada
```

## Frontera de deteccion

`appointment_availability.py` normaliza acentos y reconoce intenciones de agendar o
consultar horarios, incluyendo expresiones como `sacar cita`, junto con fechas
relativas y dias de la semana. Si encuentra una hora exacta, devuelve el control al
flujo conversacional existente.

## Consulta y respuesta

`ConversationService` construye un `ToolRequest` de `check_availability` con el rango
del dia y el `PatientScope` resuelto por el backend. El `ToolExecutor` aplica la zona
horaria, el horario laboral y el proveedor de disponibilidad configurado.

La respuesta convierte los slots a la zona horaria de la agenda, deduplica horarios
que aparecen en varios calendarios y los presenta como una lista simple. No expone IDs
internos ni ejecuta una mutacion. Despues de una respuesta exitosa, el backend persiste
la fecha, los slots ofrecidos y una expiracion de 10 minutos en
`pending_appointment_availability` dentro de `conversations.context_json`.

`format_availability_reply()` usa `format_patient_time()` para expresar cada extremo
en formato de 12 horas con AM/PM. La hora se calcula sin depender del locale; no
lleva cero inicial, y los minutos siempre tienen dos digitos. Un intervalo que
cruza mediodia se presenta como `11:30 AM a 12:00 PM`. Este formato se comparte
con las opciones de cita para reprogramar. La conversion afecta la presentacion;
los timestamps ISO persistidos conservan la zona horaria para validar la seleccion.
La instruccion final invita a continuar la solicitud sin prometer que el motivo
sea el siguiente dato; sirve tambien si el nombre acompaña una lista renovada.

En el siguiente mensaje, `ConversationService` interpreta la hora expresada por el
paciente y la compara con los slots persistidos en la zona horaria de la agenda. Una
seleccion valida se transforma en una solicitud pendiente de `create_appointment`
generada por el backend, que reutiliza la frontera de recoleccion de nombre y motivo.
El LLM no recibe ese turno y no puede reemplazar la pregunta fija con una respuesta
natural que pierda el estado. Una seleccion invalida conserva el estado y devuelve una
aclaracion controlada. El estado vencido se elimina sin modificar el calendario.

Antes de validar la seleccion, el router de
`specs/016-conversation-intent-routing/` permite abandonar la reserva o procesar otra
solicitud explicita. `cancela` sin objeto claro pide aclaracion y conserva la lista; una
pregunta nueva se procesa sin quedar atrapada en la seleccion anterior.
Las selecciones completas `quisiera una cita a las 9 am` y variantes se reconocen
antes de las reglas de gestion nueva. Conservan la fecha de la lista y pasan
directamente a `PendingAppointmentReason`, sin una captura textual del nombre
decidida por el LLM. El reconocimiento completo excluye otra cita o fecha.

El `SYSTEM_PROMPT` y el esquema de `check_availability` mantienen la misma regla para
las fechas que no entren en el detector determinista. Estas instrucciones son una
defensa adicional; no sustituyen la validacion backend para las listas generadas por el
detector.
