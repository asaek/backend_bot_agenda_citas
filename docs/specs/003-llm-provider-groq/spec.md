# 003 - Contrato LLM y proveedores compatibles con OpenAI

## Estado

Verificado para el adaptador compatible con OpenAI, la construccion del contexto
y el ciclo integrado de generacion y envio. Groq es el proveedor predeterminado
y OpenRouter usa el mismo adaptador.

## Problema

El backend no tiene una frontera estable para comunicarse con un modelo de
lenguaje. La respuesta conversacional actual esta fija y no permite cambiar de
proveedor sin modificar la logica del servicio.

## Objetivo

Definir un contrato independiente del proveedor y una implementacion inicial
para proveedores compatibles con OpenAI que pueda probarse sin realizar
llamadas reales a Internet.

## Alcance

- Definir `LLMProvider.generate(messages) -> str`.
- Representar los mensajes mediante `ChatMessage`.
- Cargar la configuracion del LLM desde variables de entorno.
- Implementar un adaptador mediante el formato de API compatible con OpenAI.
- Traducir fallos de red, HTTP y respuestas invalidas a errores propios.
- Permitir inyectar un cliente HTTP falso durante las pruebas.
- Construir los mensajes del modelo desde el historial persistido.
- Aplicar un prompt de sistema con las reglas conversacionales del MVP.
- Inyectar el proveedor en `ConversationService`.
- Generar la respuesta antes de enviarla mediante WhatsApp.
- Registrar fallos de generacion o envio para permitir reintentos.

## Requisitos funcionales

### RF-301 - Contrato independiente

El codigo consumidor debe depender del protocolo `LLMProvider` y no de una
clase especifica de Groq.

### RF-302 - Configuracion externa

El adaptador debe leer `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`,
`LLM_BASE_URL`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_HISTORY_MESSAGES` y
`LLM_MAX_OUTPUT_TOKENS`, `LLM_MAX_RESPONSE_CHARACTERS` desde el entorno, con
valores predeterminados solamente para limites tecnicos y las URLs de los
proveedores compatibles soportados.

### RF-303 - Solicitud al proveedor

El adaptador debe enviar los mensajes al endpoint `/chat/completions` del
proveedor configurado, con autenticacion Bearer, el modelo configurado y el
limite de salida configurado.

### RF-304 - Respuesta de texto

Una respuesta valida del proveedor debe convertirse en una cadena sin espacios
innecesarios al inicio o al final.

### RF-305 - Errores controlados

La ausencia de configuracion, los errores HTTP, los errores de red y las
respuestas sin contenido deben producir errores del modulo LLM, sin exponer la
respuesta completa del proveedor.

### RF-306 - Construccion del contexto

`ConversationService` debe recuperar el historial mediante `get_history()` y
convertir los mensajes persistidos a `ChatMessage`. El contexto debe comenzar
con un mensaje `system`, mapear mensajes entrantes a `user`, respuestas salientes
enviadas a `assistant` y conservar el orden cronologico. Debe limitarse a los
mensajes mas recientes configurados para evitar un contexto innecesariamente
grande.

### RF-307 - Reglas del asistente

El mensaje `system` debe indicar que el asistente responda en español, sea breve
y claro, no invente citas, horarios o datos, no afirme acciones externas, no
proporcione diagnosticos medicos, pida aclaraciones cuando falte informacion y
responda solo con texto normal.

### RF-308 - Ciclo de respuesta

`ConversationService` debe recuperar el historial, construir los mensajes del
LLM y solicitar la respuesta mediante `LLMProvider.generate()`. `main.py` debe
coordinar el servicio, `WhatsAppClient` y el registro de la respuesta, sin
contener reglas de conversacion.

### RF-309 - Fallos de generacion

Si el LLM no genera una respuesta, el backend debe registrar el fallo y enviar
la respuesta controlada. Si WhatsApp tambien falla, debe registrar esa salida
como `failed` y permitir reintentar el mensaje entrante posteriormente.

### RF-310 - Respuesta controlada

La respuesta controlada debe ser: `En este momento no pude procesar tu mensaje.
Intenta nuevamente en unos minutos.`

## Criterios de aceptacion

1. Una configuracion valida crea el adaptador para Groq.
2. Una configuracion sin API key o modelo es rechazada.
3. Los limites opcionales usan los valores definidos para esta etapa.
4. El request contiene el modelo, los mensajes y `max_tokens`.
5. La respuesta del proveedor se devuelve como texto limpio.
6. Un error HTTP se expone como `LLMProviderError`.
7. Las pruebas usan un transporte HTTP simulado y no requieren API key real.
8. Una configuracion valida para OpenRouter usa el mismo adaptador y endpoint.
9. El contexto recupera el historial guardado y conserva el orden de sus roles.
10. El contexto empieza con las reglas del mensaje `system` definidas para el MVP.
11. El contexto solo usa los mensajes mas recientes dentro del limite configurado.
12. Un mensaje valido genera la respuesta mediante el proveedor, la envia por
    WhatsApp y la registra como `sent`.
13. Una API key ausente, un timeout, un error HTTP, una respuesta vacia o una
    respuesta demasiado larga registran el tipo de fallo en SQLite.
14. Un fallo del LLM envia la respuesta controlada y la registra como `sent` si
    WhatsApp esta disponible.

## Fuera de alcance

- Reintentos, colas y procesamiento asincrono externo.
- Herramientas, RAG y memoria semantica.
- Uso de datos reales de pacientes.
