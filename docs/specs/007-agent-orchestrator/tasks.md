# Tareas - Orquestador del agente

## Implementacion

- [x] Crear `AgentOrchestrator`.
- [x] Convertir `ToolCall` en `ToolRequest` con `PatientScope` backend.
- [x] Ejecutar `ToolExecutor` y recibir `ToolResult`.
- [x] Entregar mensajes `assistant` y `tool` al siguiente turno LLM.
- [x] Sanear identificadores de paciente y calendario en resultados.
- [x] Añadir límite configurable de iteraciones.
- [x] Integrar el orquestador como dependencia de `ConversationService`.

## Pruebas

- [x] Probar una llamada válida y una respuesta final.
- [x] Probar el rechazo de paciente y calendario controlados por el LLM.
- [x] Probar serialización segura de `ToolResult`.
- [x] Probar el límite de iteraciones.
- [x] Verificar el ciclo completo desde el webhook con un ejecutor inyectado.
- [x] Ejecutar la suite en la Raspberry Pi.

## Siguiente incremento

- [ ] Configurar el proveedor real de calendario.
- [ ] Persistir y auditar las operaciones de agenda.
- [ ] Soportar varias llamadas paralelas si el proveedor las entrega.
