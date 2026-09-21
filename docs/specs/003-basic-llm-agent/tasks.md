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

## Verificacion

- [x] Probar la construccion del request de Groq y OpenRouter sin Internet.
- [x] Probar configuracion incompleta e invalida.
- [x] Probar respuestas HTTP fallidas y sin contenido.
- [x] Ejecutar la suite para confirmar el ciclo integrado con el proveedor
  simulado.

## Siguiente incremento

- [x] Construir los mensajes del LLM desde el historial de SQLite.
- [x] Definir el prompt de sistema y el limite del historial.

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
