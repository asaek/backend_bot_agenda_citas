# 005 - Contrato de herramientas de citas

## Estado

En implementacion. El modelo de dominio, los contratos de entrada/salida, la
validacion previa al proveedor y la frontera de errores publicos estan definidos
y verificados; la ejecucion y los proveedores concretos quedan pendientes.

## Objetivo

Establecer una frontera estable para que el backend valide y ejecute operaciones
de agenda sin depender de Google Calendar ni de los argumentos controlados por
el LLM.

## Incremento actual: modelo de dominio y contratos

El modelo define los siguientes conceptos:

- `Appointment`: una cita de 30 minutos asociada con un paciente y un calendario.
- `AppointmentStatus`: estado de la cita (`scheduled`, `confirmed`, `cancelled`,
  `completed` o `no_show`).
- `AvailableSlot`: periodo libre de 30 minutos en un calendario configurado.
- `ToolRequest`: solicitud de una herramienta enriquecida por el backend con el
  alcance del paciente.
- `ToolResult`: resultado exitoso o error tipificado de una herramienta.
- `PatientScope`: paciente y conversacion identificados por el backend a partir
  del contexto de WhatsApp.
- `CalendarProvider`: contrato asincrono para consultar y modificar calendarios.

Las cinco herramientas tienen estos contratos:

| Herramienta | Argumentos del LLM | Salida normalizada |
|---|---|---|
| `check_availability` | `start_at`, `end_at` | `CheckAvailabilityOutput` |
| `create_appointment` | `start_at`, `reason` | `CreateAppointmentOutput` |
| `list_appointments` | `start_at`, `end_at` opcionales | `ListAppointmentsOutput` |
| `reschedule_appointment` | `appointment_id`, `new_start_at` | `RescheduleAppointmentOutput` |
| `cancel_appointment` | `appointment_id` | `CancelAppointmentOutput` |

Las fechas se reciben como valores ISO y se normalizan usando la zona horaria
predeterminada del backend. Los inputs tipados incluyen `PatientScope`, pero no
incluyen duracion, calendario, zona horaria, usuario ni identificadores de
conversacion.

## Validacion previa al proveedor

`validate_tool_input()` recibe el input tipado, el horario laboral, el instante
actual y las citas existentes conocidas. Antes de delegar en un proveedor:

- Rechaza fechas pasadas.
- Comprueba que una cita de 30 minutos cabe dentro del horario laboral.
- Rechaza solapamientos con citas `scheduled` o `confirmed`.
- Ignora citas canceladas, completadas o marcadas como `no_show` al calcular
  bloqueos.
- Verifica que una cita pertenece al paciente del `PatientScope`.
- Verifica que las transiciones de reprogramacion y cancelacion sean validas.
- Devuelve errores tipificados mediante `ToolValidationError`.

## Errores publicos

La frontera de agenda expone unicamente errores propios del backend:

- `InvalidToolArguments`.
- `SlotUnavailable`.
- `OutsideBusinessHours`.
- `AppointmentNotFound`.
- `AppointmentAccessDenied`.
- `InvalidAppointmentState`.
- `CalendarProviderUnavailable`.
- `CalendarProviderError`.

`tool_results.py` convierte esos errores, los errores de validacion y las
excepciones desconocidas de un proveedor en `ToolResult.failure()`. El resultado
solo contiene un codigo, un mensaje estable en lenguaje natural y si es seguro
reintentar. Nunca copia el texto de una excepcion de Google o de otro proveedor.
Los errores transitorios reconocibles se clasifican como
`CalendarProviderUnavailable`; los demas fallos externos se reducen a
`CalendarProviderError`.

## Reglas de dominio

1. Las citas y los espacios disponibles duran exactamente 30 minutos.
2. Todas las fechas deben incluir una zona horaria explicita.
3. Un periodo ocupado no puede ofrecerse como espacio disponible.
4. Una cita cancelada no puede reprogramarse.
5. Una cita inexistente no puede modificarse.
6. El paciente se obtiene de `PatientScope`, nunca de un `patient_id` enviado por
   el LLM.
7. Los identificadores de calendarios pertenecen a la configuracion del backend y
   no forman parte de los argumentos controlados por el LLM.

## Criterios de aceptacion del incremento

1. El modelo rechaza citas y espacios que no duren 30 minutos.
2. El modelo rechaza fechas sin zona horaria o intervalos invalidos.
3. Una cita cancelada se identifica como no reprogramable.
4. `ToolRequest` siempre contiene un `PatientScope` del backend.
5. `ToolRequest` rechaza argumentos de paciente o calendario controlados por el
   backend.
6. `ToolResult` no puede representar simultaneamente exito y error, ni un fallo
   con datos de exito.
7. `CalendarProvider` declara las cinco operaciones necesarias sin exponer una
   implementacion concreta de Google.
8. Cada herramienta rechaza argumentos desconocidos o incompletos.
9. Los inputs normalizados conservan el alcance del paciente y las fechas con
   zona horaria.
10. Las salidas de colecciones son inmutables y especificas para cada herramienta.
11. Las solicitudes de crear o reprogramar no aceptan fechas pasadas ni fuera del
    horario laboral.
12. Las solicitudes no aceptan solapamientos con citas activas.
13. Las modificaciones rechazan citas de otro paciente, inexistentes o en un
    estado no modificable.
14. Las ocho clases de error publico tienen codigos y mensajes estables.
15. Una excepcion desconocida de un proveedor se convierte en un error publico
    sin incluir su mensaje interno.
16. Un fallo transitorio del proveedor se marca como reintentable sin exponer la
    excepcion original.

## Fuera de alcance de este incremento

- Ejecutar las cinco herramientas mediante un `ToolExecutor` completo.
- Implementar `FakeCalendarProvider`.
- Conectar Google Calendar.
- Crear tablas persistentes de citas.
- Integrar llamadas de herramientas en el contrato actual del LLM.
