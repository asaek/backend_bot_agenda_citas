# 009 - Adaptador de Google Calendar

## Estado

Implementado y verificado con HTTP simulado en el mirror. La disponibilidad puede
activarse de forma incremental contra Google; la verificacion real requiere
credenciales y calendarios externos que no se guardan en el repositorio.

## Objetivo

Conectar el contrato `CalendarProvider` con Google Calendar sin exponer
credenciales, identificadores internos ni control del paciente al LLM.

## Alcance

- Seleccionar `FakeCalendarProvider` o `GoogleCalendarProvider` mediante
  `CALENDAR_PROVIDER`, usando el fake por defecto.
- Seleccionar un proveedor independiente para `check_availability` mediante
  `CALENDAR_AVAILABILITY_PROVIDER`, usando el proveedor principal por defecto.
- Autenticar mediante OAuth con access/refresh token o mediante cuenta de servicio.
- Configurar uno o varios calendarios desde `GOOGLE_CALENDAR_IDS`, con el limite de
  50 calendarios impuesto por `freeBusy`.
- Consultar disponibilidad con `freeBusy.query` y generar slots de 30 minutos.
- Crear, reprogramar y cancelar eventos en los calendarios configurados.
- Guardar `managed_by`, `patient_id` y `conversation_id` como propiedades privadas.
- Listar citas vigentes del paciente mediante `events.list`, filtrando propiedades
  privadas, excluyendo eventos cancelados y siguiendo `nextPageToken`.
- Traducir eventos validos al modelo `Appointment` sin sustituir el `PatientScope`
  resuelto por el backend.
- Reprogramar debe localizar el evento administrado del paciente, comprobar el nuevo
  intervalo con `freeBusy` en su calendario actual y aplicar un `PATCH` solo cuando
  el horario este libre.
- Cancelar debe aplicar `status=cancelled` mediante `PATCH`, conservar el evento en
  Google y devolver una cita cancelada aunque la respuesta no incluya sus fechas.
- Convertir errores de autenticacion, red y API a errores publicos del dominio.

## Requisitos funcionales

### RF-901 - Composicion configurable

`main.py` debe conservar el fake como valor por defecto. `CALENDAR_PROVIDER`
selecciona el proveedor principal; `CALENDAR_AVAILABILITY_PROVIDER` puede
seleccionar Google solo para `check_availability` sin activar las demas
operaciones.

### RF-902 - Disponibilidad

El adaptador debe consultar todos los calendarios configurados en una sola llamada
`freeBusy.query`, tratar todos los periodos ocupados como no disponibles y devolver
slots consecutivos de 30 minutos.

### RF-903 - Alcance y propiedades privadas

Las escrituras deben usar el `PatientScope` recibido por el backend y guardar sus
identificadores en propiedades privadas. Las lecturas y modificaciones deben exigir
el marcador `managed_by=whatsapp_chatbot` y el `patient_id` del alcance actual.

### RF-904 - Eventos y paginacion

La lista debe consultar cada calendario configurado, aplicar los limites opcionales,
seguir todas las paginas y devolver solo citas vigentes ordenadas por inicio. La
consulta no debe solicitar tombstones cancelados con `showDeleted=true`. Reprogramar
y cancelar deben modificar el evento existente sin eliminarlo.

### RF-906 - Sincronizacion de mutaciones

Crear, reprogramar y cancelar deben usar `sendUpdates=all`. El adaptador no agrega
asistentes, por lo que esta opcion no envia avisos al paciente; evita el modo
`sendUpdates=none`, que Google advierte que puede perder eventos o impedir su
sincronizacion.

### RF-905 - Seguridad operacional

Los secretos deben recibirse desde el entorno o archivos montados fuera del
repositorio. Los detalles de Google no deben aparecer en `ToolResult` ni en el
contexto enviado al LLM.

## Criterios de aceptacion

1. `uv sync` instala la dependencia de autenticacion declarada.
2. El fake existente sigue siendo el proveedor predeterminado.
3. OAuth y cuenta de servicio producen un proveedor configurado sin credenciales en
   el codigo fuente.
4. `freeBusy` consulta todos los calendarios y excluye periodos ocupados.
5. `check_availability` no devuelve slots fuera de `BusinessHours` aunque el
   rango solicitado los incluya.
6. `BusinessHours` puede configurarse mediante `BUSINESS_WORKDAYS`,
   `BUSINESS_HOURS_START` y `BUSINESS_HOURS_END`.
7. La creacion guarda las tres propiedades privadas y devuelve un `Appointment`.
8. La lista sigue paginas y solo devuelve eventos vigentes administrados por este
   sistema y pertenecientes al paciente solicitado.
9. Reprogramar y cancelar respetan acceso, estado y conflictos; un evento cancelado
   aunque Google lo devuelva sin fechas no puede reprogramarse y una cancelacion no
   puede devolverse como activa.
10. Las mutaciones usan `sendUpdates=all` y las pruebas lo verifican.
11. Las pruebas no hacen llamadas de red real y cubren errores transitorios.

## Fuera del alcance

- Descubrir calendarios automaticamente.
- Interpretar o modificar eventos existentes sin propiedades privadas del sistema.
- Persistir citas en SQLite ademas de Google Calendar.
- Resolver festivos, ausencias u horario laboral dentro del adaptador; esas reglas
  siguen perteneciendo a `ToolExecutor` y `BusinessHours`.
- Verificar credenciales reales en CI o en la suite automatizada.
