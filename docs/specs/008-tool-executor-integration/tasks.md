# Tareas - Integracion del ToolExecutor

## Implementacion

- [x] Crear la composicion de `CalendarProvider` y `FakeCalendarProvider` en
  `main.py`.
- [x] Configurar `BusinessHours` para el runtime del MVP tecnico.
- [x] Crear `ToolExecutor` y conservarlo en `app.state`.
- [x] Hacer que `ConversationService` reciba el ejecutor y cree el orquestador.
- [x] Mantener la creacion de `ToolRequest` con `PatientScope` backend.

## Pruebas

- [x] Probar la composicion por defecto con `FakeCalendarProvider`.
- [x] Probar `ConversationService` con una llamada y una respuesta final.
- [x] Probar el webhook completo con el ejecutor configurado.
- [x] Ejecutar la suite en la Raspberry Pi.

## Siguiente incremento

- [ ] Reemplazar `FakeCalendarProvider` por un proveedor de calendario real.
- [ ] Cargar horarios, festivos y bloqueos desde una configuracion persistente.
