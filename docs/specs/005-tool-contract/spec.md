# 005 - Contrato de herramientas de citas

## Estado

Verificado. El modelo de dominio, los contratos de entrada/salida, la validacion
previa al proveedor, la frontera de errores publicos, el proveedor falso en
memoria y el ejecutor estan implementados y probados; Google Calendar queda
pendiente.

## Objetivo

Establecer una frontera estable para que el backend valide y ejecute operaciones
de agenda sin depender de Google Calendar ni de los argumentos controlados por
el LLM.

## Incremento actual: proveedor falso determinista

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
predeterminada del backend. Los inputs tipados incluyen `PatientScope`, que
transporta el paciente y la conversacion resueltos por el backend. Los
argumentos controlados por el LLM no incluyen duracion, calendario, zona horaria,
usuario ni identificadores de paciente o conversacion.

`list_appointments` acepta la ausencia total del rango o un par completo de
`start_at` y `end_at`. Sin rango devuelve las citas visibles del paciente actual;
con rango devuelve las citas que se superponen con el intervalo solicitado,
incluidas las canceladas. La consulta no exige horario laboral ni fecha futura,
porque tambien puede consultar historial. La pertenencia al paciente sigue
siendo responsabilidad del proveedor configurado.

## Validacion previa al proveedor

`validate_tool_input()` recibe el input tipado, el horario laboral, el instante
actual y las citas existentes conocidas. Antes de delegar en un proveedor:

- Rechaza fechas pasadas al crear o reprogramar citas.
- Comprueba que una cita de 30 minutos cabe dentro del horario laboral.
- Rechaza solapamientos con citas `scheduled` o `confirmed`.
- Ignora citas canceladas, completadas o marcadas como `no_show` al calcular
  bloqueos.
- Permite consultar citas pasadas mediante `list_appointments`.
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

## FakeCalendarProvider

`FakeCalendarProvider` implementa el mismo `CalendarProvider` asincrono sin red ni
persistencia. Permite configurar calendarios, periodos ocupados y citas iniciales
deterministas. Las citas nuevas reciben identificadores secuenciales y las
operaciones usan siempre el primer calendario disponible en el orden configurado.

El fake consulta slots de 30 minutos, considera ocupados los periodos registrados
y las citas activas, y conserva las citas canceladas para poder consultarlas. Sus
operaciones de crear y reprogramar rechazan conflictos con `SlotUnavailable`.
Tambien permite configurar errores publicos persistentes o de una sola ejecucion
para probar la traduccion de errores del proveedor.

## ToolExecutor

`ToolExecutor.execute()` recibe un `ToolRequest` directo, sin depender del
formato de tool calling de un LLM. Parsea y normaliza sus argumentos, conserva el
`PatientScope` creado por el backend, valida reglas locales y, cuando la regla
depende de citas conocidas, obtiene una fotografia mediante el proveedor usando
ese mismo alcance.

Luego ejecuta exactamente una operacion de `CalendarProvider` y envuelve su salida
en el output tipado correspondiente. Devuelve siempre `ToolResult`: los errores de
argumentos, reglas de negocio y proveedor se convierten mediante la frontera de
errores publicos. El request no puede elegir paciente, conversacion ni calendario;
el calendario lo resuelve la configuracion del proveedor.

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
17. El fake implementa las cinco operaciones del `CalendarProvider` sin red ni
    persistencia.
18. Los periodos ocupados bloquean los slots correspondientes.
19. Las citas creadas, reprogramadas y canceladas conservan estados e
    identificadores deterministas.
20. Los conflictos de crear y reprogramar producen `SlotUnavailable`.
21. Los errores simulados pueden ser persistentes o de una sola ejecucion.
22. `ToolExecutor` rechaza argumentos invalidos antes de ejecutar operaciones del
    proveedor.
23. `ToolExecutor` aplica horario laboral, fechas futuras, conflictos conocidos,
    pertenencia y estados antes de delegar cuando dispone de la fotografia.
24. Cada operacion del ejecutor devuelve el output tipado correspondiente dentro
    de `ToolResult.success()`.
25. El ejecutor conserva el `PatientScope` del request y no permite seleccionar
    paciente, conversacion ni calendario desde los argumentos.
26. `list_appointments` devuelve solo citas del paciente actual y aplica el rango
    opcional por superposicion, incluso cuando el rango pertenece al historial.

## Cierre del incremento

- [x] Las cinco herramientas tienen contratos documentados.
- [x] Las entradas y salidas estan tipadas.
- [x] Las validaciones ocurren antes del proveedor.
- [x] `FakeCalendarProvider` implementa las cinco operaciones.
- [x] El backend de agenda ejecuta solicitudes mediante `ToolExecutor`.
- [x] Los errores tienen una clasificacion y mensajes estables.
- [x] Las pruebas cubren exito, conflicto, permisos y errores.
- [x] No existe dependencia de Google Calendar.

El cierre se refiere a la frontera interna del backend y a su proveedor falso.
La ejecucion de tool calls desde `ConversationService` y un proveedor real de
Google Calendar no forman parte de este incremento.

## Fuera de alcance de este incremento

- Conectar Google Calendar.
- Crear tablas persistentes de citas.
- Ejecutar tool calls dentro del ciclo conversacional.
