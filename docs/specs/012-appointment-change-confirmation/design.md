# Diseno - Confirmacion de cambios de citas

## Estado

Verificado en Raspberry Pi. La confirmacion se aplica antes de ejecutar el proveedor de calendario y
conserva la integracion de eventos y notificaciones existente.

## Flujo implementado

```text
Mensaje del paciente
    |
    v
ConversationService
    |
    +-- accion pendiente existente?
    |       |
    |       +-- Si -> ejecutar la accion exacta
    |       +-- No -> continuar con el agente
    |
    v
AgentOrchestrator
    |
    +-- cancel/reschedule -> resolver cita en alcance
    |                        |-- ausente/fallo -> error publico, sin estado pendiente
    |                        +-- encontrada -> guardar accion y pedir Si/No
    |                                          sin modificar el calendario
    |
    +-- confirmacion afirmativa -> ToolExecutor -> CalendarProvider
                                             |
                                             v
                                  evento y notificacion al doctor
```

## Frontera de confirmacion

`AgentOrchestrator` recibe un manejador previo a la ejecucion de herramientas.
`ConversationService` intercepta solo `cancel_appointment` y
`reschedule_appointment` y valida la forma basica de sus argumentos. Antes de persistir
la accion o construir la pregunta, obtiene mediante `ToolExecutor` una cita del alcance
del paciente. Si el ID no aparece, devuelve `appointment_not_found`; si falla la lectura,
normaliza la excepcion a su error publico de agenda. En ambos casos termina el turno sin
accion pendiente, confirmacion ni mutacion. Solo una cita recuperada permite mostrar
fecha, horario y motivo y guardar la operacion exacta.

La accion pendiente conserva el nombre de la herramienta, sus argumentos permitidos,
el ID de la llamada, los tiempos de creacion y expiracion y los datos recuperados de la
cita. Se almacena dentro de `conversations.context_json`, preservando cualquier otro
contexto existente. No existe una accion pendiente si la consulta no recupera una cita.

## Resolucion

En el siguiente mensaje, `ConversationService` clasifica la intencion de la respuesta
normalizada como afirmativa, negativa o ambigua. Reconoce expresiones afirmativas y
negativas claras aunque incluyan cortesia, por ejemplo `Si, por favor` o `No,
gracias`. Si encuentra señales contradictorias o de incertidumbre, conserva la
accion y pide aclaracion. Una afirmacion reconstruye la llamada almacenada y la
ejecuta mediante `AgentOrchestrator.execute_confirmed_tool()`; una respuesta
negativa limpia el estado sin tocar el calendario.

La confirmacion expira a los 10 minutos. El estado se limpia antes de una ejecucion
confirmada para evitar reutilizar la misma autorizacion.

## Integracion con notificaciones

La primera solicitud devuelve solamente la pregunta de confirmacion con los datos
publicables de la cita y no emite un `AppointmentNotificationEvent`. El evento se
crea unicamente cuando la operacion confirmada devuelve un resultado exitoso, por
lo que el flujo existente de entrega al doctor permanece aislado y con idempotencia.
