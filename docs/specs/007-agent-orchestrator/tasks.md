# Tareas - Orquestador del agente

## Implementacion

- [x] Crear `AgentOrchestrator`.
- [x] Convertir `ToolCall` en `ToolRequest` con `PatientScope` backend.
- [x] Ejecutar `ToolExecutor` y recibir `ToolResult`.
- [x] Entregar mensajes `assistant` y `tool` al siguiente turno LLM.
- [x] Sanear identificadores de paciente y calendario en resultados.
- [x] Indicar que los IDs internos de citas no se muestran al paciente.
- [x] Convertir tablas Markdown de citas en listas compatibles con WhatsApp.
- [x] Añadir límite configurable de iteraciones.
- [x] Integrar el orquestador como dependencia de `ConversationService`.

## Pruebas

- [x] Probar una llamada válida y una respuesta final.
- [x] Probar el rechazo de paciente y calendario controlados por el LLM.
- [x] Probar serialización segura de `ToolResult`.
- [x] Verificar la redaccion de detalles de citas sin ID interno.
- [x] Verificar que una tabla de citas se entregue como lista sin ID interno.
- [x] Probar el límite de iteraciones.
- [x] Verificar el ciclo completo desde el webhook con un ejecutor inyectado.
- [x] Ejecutar la suite en la Raspberry Pi.

## Siguiente incremento

- [ ] Configurar el proveedor real de calendario.
- [ ] Persistir y auditar las operaciones de agenda.
- [ ] Soportar varias llamadas paralelas si el proveedor las entrega.
