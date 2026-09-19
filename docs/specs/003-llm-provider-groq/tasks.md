# Tareas - Contrato LLM y proveedores compatibles con OpenAI

## Implementacion

- [x] Definir `ChatMessage` y el protocolo `LLMProvider`.
- [x] Definir `LLMSettings` y cargar la configuracion desde el entorno.
- [x] Validar credenciales, modelo y limites numericos.
- [x] Implementar `OpenAICompatibleLLMProvider` con `httpx`.
- [x] Normalizar respuestas y errores del proveedor.
- [x] Permitir inyeccion de transporte HTTP para pruebas.

## Verificacion

- [x] Probar la construccion del request de Groq y OpenRouter sin Internet.
- [x] Probar configuracion incompleta e invalida.
- [x] Probar respuestas HTTP fallidas y sin contenido.
- [x] Ejecutar la suite existente para confirmar que el webhook sigue usando la
  respuesta fija.

## Siguiente incremento

- [x] Construir los mensajes del LLM desde el historial de SQLite.
- [x] Definir el prompt de sistema y el limite del historial.

## Integracion pendiente

- [ ] Inyectar el proveedor en `ConversationService`.
- [ ] Reemplazar la respuesta fija y registrar los fallos de generacion.
