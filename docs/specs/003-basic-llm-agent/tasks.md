# Tareas - Agente LLM basico

## Implementacion

- [x] Definir `ChatMessage` y el protocolo `LLMProvider`.
- [x] Definir `LLMResponse` para respuestas de texto y `ToolCall`.
- [x] Definir `LLMSettings` y cargar la configuracion desde el entorno.
- [x] Validar credenciales, modelo y limites numericos.
- [x] Implementar `OpenAICompatibleLLMProvider` con `httpx`.
- [x] Normalizar respuestas y errores del proveedor.
- [x] Normalizar tool calls nativos y argumentos JSON de objeto.
- [x] Permitir inyeccion de transporte HTTP para pruebas.
- [x] Definir el agente basico mediante `ConversationService` y `LLMProvider`.
- [x] Seleccionar claves, modelos y URLs por proveedor para Groq, OpenAI y OpenRouter.
- [x] Usar Responses API y `max_output_tokens` para OpenAI; preservar Chat
  Completions para Groq y OpenRouter.
- [x] Documentar que el ID de modelo se pasa directamente y debe admitir el endpoint
  y las herramientas soportados por el adaptador.

## Verificacion

- [x] Probar requests de Groq, OpenAI Responses y OpenRouter sin Internet.
- [x] Probar tool calling de Responses y reproducir sus elementos de razonamiento
  junto con la salida de herramienta.
- [x] Verificar que el selector elige las credenciales y el modelo del proveedor
  configurado y acepta `LLM_API_KEY`/`LLM_MODEL` como fallback del proveedor activo.
- [x] Probar configuracion incompleta e invalida.
- [x] Probar respuestas HTTP fallidas y sin contenido.
- [x] Ejecutar la suite para confirmar el ciclo integrado con el proveedor
  simulado.

## Siguiente incremento

- [x] Construir los mensajes del LLM desde el historial de SQLite.
- [x] Definir el prompt de sistema y el limite del historial.
- [x] Inyectar fecha, hora, zona horaria y rangos relativos en el prompt de agenda.

## Integracion del ciclo

- [x] Inyectar el proveedor en `ConversationService`.
- [x] Reemplazar la respuesta fija y registrar los fallos de generacion.
- [x] Coordinar generacion, envio y persistencia desde `main.py`.

## Manejo de errores

- [x] Clasificar timeouts, errores HTTP, respuestas vacias y respuestas demasiado largas.
- [x] Enviar una respuesta controlada cuando falle el LLM.
- [x] Registrar los fallos del LLM en SQLite.

## Pruebas del agente sin API

- [x] Crear y reutilizar `FakeLLMProvider` en las pruebas automaticas.
- [x] Verificar la transformacion del historial y el mensaje actual.
- [x] Verificar el envio de la respuesta y su persistencia como `sent`.
- [x] Verificar que un webhook duplicado no vuelve a llamar al LLM.
- [x] Verificar que los errores del LLM quedan registrados.
- [x] Verificar la respuesta de verificacion de Meta.
- [x] Ejecutar la suite sin credenciales ni servicios externos.
- [x] Probar que "hoy" se resuelve con el rango del reloj configurado.
- [x] Persistir el codigo HTTP del proveedor y migrar la columna sin perder filas previas.
- [x] Registrar solo tipo y codigo HTTP, sin imprimir el contenido entrante.
