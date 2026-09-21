# Tareas - Persistencia de citas

## Implementacion

- [x] Definir la tabla `appointments` y sus restricciones SQLite.
- [x] Definir `AppointmentRecord` con IDs, paciente, estado y fechas de sincronizacion.
- [x] Implementar `AppointmentRepository` para buscar y actualizar citas.
- [x] Implementar `PersistentCalendarProvider` como mapeo de IDs.
- [x] Envolver el proveedor Google en el runtime configurado.

## Pruebas

- [x] Probar insercion y upsert sin cambiar el ID interno.
- [x] Probar mapeo create/list/reschedule/cancel entre IDs internos y Google.
- [x] Probar `last_synced_at` y preservacion del registro cancelado.
- [x] Probar aislamiento entre pacientes.
- [x] Ejecutar la suite completa de esta iteracion en Raspberry Pi.

## Fuera de este corte

- [ ] Implementar reconciliacion periodica o sincronizacion en segundo plano.
- [ ] Migrar eventos Google historicos que no tengan metadatos del chatbot.
