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
Flujo normal de create_appointment y pregunta por motivo
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
internos ni ejecuta una mutacion.

El `SYSTEM_PROMPT` y el esquema de `check_availability` mantienen la misma regla para
las fechas que no entren en el detector determinista.
