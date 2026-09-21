# Tareas - Contrato de tool calling del LLM

## Implementacion

- [x] Definir `ToolCall` y `LLMResponse`.
- [x] Ampliar `LLMProvider.generate()` para devolver texto o tool call.
- [x] Normalizar la forma nativa compatible con OpenAI.
- [x] Normalizar la forma interna `tool_call`.
- [x] Validar nombre, argumentos y multiplicidad de llamadas.
- [x] Mantener el limite de longitud para respuestas textuales.
- [x] Enviar los esquemas de las cinco herramientas al proveedor.
- [x] Evitar enviar tool calls como texto a WhatsApp.

## Pruebas

- [x] Conservar las pruebas de respuestas textuales.
- [x] Probar una respuesta nativa con `function.arguments` JSON.
- [x] Probar una respuesta interna con argumentos objeto.
- [x] Probar argumentos invalidos y multiples tool calls.
- [x] Probar el comportamiento seguro del webhook.
- [x] Ejecutar la suite sin servicios externos.

## Siguiente incremento

- [ ] Convertir `ToolCall` en `ToolRequest` con `PatientScope` del backend.
- [ ] Ejecutar `ToolExecutor` y devolver el resultado al LLM.
