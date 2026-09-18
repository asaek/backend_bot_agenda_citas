# 003 - Contrato LLM y proveedor Groq

## Estado

Verificado para los dos primeros incrementos de la etapa 4. El contrato, el
adaptador de Groq y la construccion del contexto existen, pero el webhook
todavia conserva la respuesta fija hasta completar la integracion del proveedor.

## Problema

El backend no tiene una frontera estable para comunicarse con un modelo de
lenguaje. La respuesta conversacional actual esta fija y no permite cambiar de
proveedor sin modificar la logica del servicio.

## Objetivo

Definir un contrato independiente del proveedor y una implementacion inicial
para Groq que pueda probarse sin realizar llamadas reales a Internet.

## Alcance

- Definir `LLMProvider.generate(messages) -> str`.
- Representar los mensajes mediante `ChatMessage`.
- Cargar la configuracion del LLM desde variables de entorno.
- Implementar el adaptador de Groq mediante su API compatible con OpenAI.
- Traducir fallos de red, HTTP y respuestas invalidas a errores propios.
- Permitir inyectar un cliente HTTP falso durante las pruebas.
- Construir los mensajes del modelo desde el historial persistido.
- Aplicar un prompt de sistema con las reglas conversacionales del MVP.

## Requisitos funcionales

### RF-301 - Contrato independiente

El codigo consumidor debe depender del protocolo `LLMProvider` y no de una
clase especifica de Groq.

### RF-302 - Configuracion externa

El adaptador debe leer `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`,
`LLM_BASE_URL`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_HISTORY_MESSAGES` y
`LLM_MAX_OUTPUT_TOKENS` desde el entorno, con valores predeterminados solamente
para limites tecnicos y la URL de Groq.

### RF-303 - Solicitud a Groq

El adaptador debe enviar los mensajes al endpoint `/chat/completions` con
autenticacion Bearer, el modelo configurado y el limite de salida configurado.

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

## Criterios de aceptacion

1. Una configuracion valida crea un proveedor Groq.
2. Una configuracion sin API key o modelo es rechazada.
3. Los limites opcionales usan los valores definidos para esta etapa.
4. El request contiene el modelo, los mensajes y `max_tokens`.
5. La respuesta del proveedor se devuelve como texto limpio.
6. Un error HTTP se expone como `LLMProviderError`.
7. Las pruebas usan un transporte HTTP simulado y no requieren API key real.
8. El contexto recupera el historial guardado y conserva el orden de sus roles.
9. El contexto empieza con las reglas del mensaje `system` definidas para el MVP.
10. El contexto solo usa los mensajes mas recientes dentro del limite configurado.
11. El webhook existente conserva su respuesta fija hasta la integracion del
    proveedor.

## Fuera de alcance

- Integracion del proveedor en `POST /webhook/whatsapp`.
- Reintentos, colas y procesamiento asincrono externo.
- Herramientas, RAG y memoria semantica.
- Uso de datos reales de pacientes.
