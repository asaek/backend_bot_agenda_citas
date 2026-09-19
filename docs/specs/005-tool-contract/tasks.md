# Tareas - Contrato de herramientas de citas

## Modelo de dominio

- [x] Definir `Appointment` y la duracion fija de 30 minutos.
- [x] Definir `AppointmentStatus` y la regla de reprogramacion.
- [x] Definir `AvailableSlot` con zona horaria explicita.
- [x] Definir `PatientScope` como identidad proveniente de WhatsApp.
- [x] Definir `ToolRequest` sin argumentos de paciente o calendario.
- [x] Definir `ToolResult`, `ToolError` y codigos de error.
- [x] Definir el protocolo asincrono `CalendarProvider`.
- [x] Probar las invariantes del modelo.

## Contratos de herramientas

- [x] Definir la lista de las cinco herramientas soportadas.
- [x] Definir argumentos obligatorios y opcionales por herramienta.
- [x] Definir inputs y outputs tipados por herramienta.
- [x] Normalizar fechas con la zona horaria predeterminada del backend.
- [x] Rechazar argumentos desconocidos o controlados por el backend.
- [x] Probar los cinco contratos sin ejecutar un proveedor externo.

## Validacion previa al proveedor

- [x] Definir horarios laborales por zona horaria.
- [x] Rechazar fechas pasadas.
- [x] Rechazar citas fuera del horario laboral.
- [x] Rechazar solapamientos con citas activas.
- [x] Verificar pertenencia del paciente antes de modificar una cita.
- [x] Verificar estados validos para reprogramar y cancelar.
- [x] Clasificar errores de validacion con `ToolErrorCode`.
- [x] Probar las reglas sin realizar llamadas a un proveedor.

## Errores publicos

- [x] Definir las ocho excepciones publicas independientes del proveedor.
- [x] Asociar cada excepcion con un codigo y mensaje seguro.
- [x] Convertir errores de validacion y excepciones externas a `ToolResult`.
- [x] Clasificar fallos transitorios como reintentables sin filtrar detalles.
- [x] Probar exito, errores tipificados y excepciones desconocidas.

## FakeCalendarProvider

- [x] Implementar el protocolo `CalendarProvider` en memoria.
- [x] Registrar periodos ocupados y citas iniciales deterministas.
- [x] Crear, listar, reprogramar y cancelar citas.
- [x] Rechazar conflictos de slots y conservar citas canceladas.
- [x] Simular errores persistentes y de una sola ejecucion.
- [x] Probar operaciones, conflictos y errores del proveedor.

## ToolExecutor

- [x] Recibir `ToolRequest` y conservar su `PatientScope` del backend.
- [x] Normalizar argumentos y rechazar solicitudes invalidas antes del proveedor.
- [x] Aplicar horarios, fechas, conflictos conocidos, permisos y estados.
- [x] Despachar las cinco operaciones al `CalendarProvider`.
- [x] Construir outputs tipados dentro de `ToolResult`.
- [x] Convertir excepciones del proveedor en errores publicos seguros.
- [x] Probar el ejecutor directamente sin tool calling del LLM.

## Siguiente incremento

- [ ] Integrar las herramientas con el flujo del agente.

## Integracion futura

- [ ] Implementar el adaptador de Google Calendar.
- [ ] Verificar horario laboral, festivos, ausencias y bloqueos.
- [ ] Definir el formato de tool calling para los proveedores LLM.
