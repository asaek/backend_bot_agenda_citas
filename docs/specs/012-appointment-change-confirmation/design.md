# Diseno - Confirmacion de cambios de citas

## Estado

Implementado. La confirmacion se aplica antes de ejecutar el proveedor de calendario
y conserva la integracion de eventos y notificaciones existente.

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
    +-- cancel/reschedule -> leer datos de la cita, guardar accion y pedir Si/No
    |                        sin modificar el calendario
    |
    +-- confirmacion afirmativa -> ToolExecutor -> CalendarProvider
                                             |
                                             v
                                  evento y notificacion al doctor
```

## Frontera de confirmacion

`AgentOrchestrator` recibe un manejador previo a la ejecucion de herramientas.
`ConversationService` intercepta solo `cancel_appointment` y
`reschedule_appointment`, valida la forma basica de sus argumentos y persiste la
accion pendiente. Antes de construir la pregunta, obtiene mediante `ToolExecutor`
un snapshot de solo lectura de la cita para mostrar fecha, horario y motivo. El
proveedor no se modifica en ese primer paso.

La accion pendiente conserva el nombre de la herramienta, sus argumentos permitidos,
el ID de la llamada y sus tiempos de creacion y expiracion y, cuando la consulta fue
exitosa, los datos mostrados de la cita. Se almacena dentro de
`conversations.context_json`, preservando cualquier otro contexto existente. Si la
consulta de lectura no esta disponible, la accion sigue requiriendo confirmacion y
usa la pregunta generica.

## Resolucion

En el siguiente mensaje, `ConversationService` clasifica una respuesta afirmativa,
negativa o ambigua. Una afirmacion reconstruye la llamada almacenada y la ejecuta
mediante `AgentOrchestrator.execute_confirmed_tool()`. Una respuesta negativa limpia
el estado sin tocar el calendario. Una respuesta ambigua mantiene el estado y pide
responder `Si` o `No`.

La confirmacion expira a los 10 minutos. El estado se limpia antes de una ejecucion
confirmada para evitar reutilizar la misma autorizacion.

## Integracion con notificaciones

La primera solicitud devuelve solamente la pregunta de confirmacion con los datos
publicables de la cita y no emite un `AppointmentNotificationEvent`. El evento se
crea unicamente cuando la operacion confirmada devuelve un resultado exitoso, por
lo que el flujo existente de entrega al doctor permanece aislado y con idempotencia.
