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

En el siguiente mensaje, `ConversationService` interpreta la hora expresada por el
paciente y la compara con los slots persistidos en la zona horaria de la agenda. Una
seleccion valida se transforma en una solicitud pendiente de `create_appointment`
generada por el backend, que reutiliza la frontera de recoleccion de nombre y motivo.
El LLM no recibe ese turno y no puede reemplazar la pregunta fija con una respuesta
natural que pierda el estado. Una seleccion invalida conserva el estado y devuelve una
aclaracion controlada. El estado vencido se elimina sin modificar el calendario.

El `SYSTEM_PROMPT` y el esquema de `check_availability` mantienen la misma regla para
las fechas que no entren en el detector determinista. Estas instrucciones son una
defensa adicional; no sustituyen la validacion backend para las listas generadas por el
detector.
