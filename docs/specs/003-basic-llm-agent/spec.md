# 003 - Agente LLM basico

## Estado

Verificado para el agente LLM basico, el adaptador compatible con OpenAI, la
construccion del contexto, el ciclo integrado de generacion y envio y la seleccion
de Groq, OpenAI u OpenRouter mediante variables de entorno. OpenAI usa Responses
API y Groq/OpenRouter usan Chat Completions. Groq es el proveedor predeterminado.

## Problema

El backend no tiene una frontera estable para comunicarse con un modelo de
lenguaje. La respuesta conversacional actual esta fija y no permite cambiar de
proveedor sin modificar la logica del servicio.

## Objetivo

Definir un agente conversacional basico con un contrato independiente del
proveedor y una implementacion inicial para proveedores compatibles con OpenAI.
El ciclo debe poder probarse sin realizar llamadas reales a Internet.

## Alcance

- Definir `LLMProvider.generate(messages) -> LLMResponse`, con respuestas de texto
  o solicitudes de herramienta.
- Configurar un limite positivo de iteraciones de herramientas.
- Representar los mensajes mediante `ChatMessage`.
- Cargar la configuracion del LLM desde variables de entorno.
- Implementar un adaptador mediante el formato de API compatible con OpenAI.
- Traducir fallos de red, HTTP y respuestas invalidas a errores propios.
- Permitir inyectar un cliente HTTP falso durante las pruebas.
- Construir los mensajes del modelo desde el historial persistido.
- Aplicar un prompt de sistema con las reglas conversacionales del MVP.
- Inyectar en el prompt la fecha actual, la zona horaria de la agenda y los rangos
  de fechas relativas resueltos por el backend.
- Inyectar el proveedor en `ConversationService`.
- Generar la respuesta antes de enviarla mediante WhatsApp.
- Registrar fallos de generacion o envio para permitir reintentos.
- Persistir el tipo de fallo LLM y, para errores HTTP, el codigo numerico recibido;
  los logs no deben incluir texto del paciente, credenciales ni cuerpos del proveedor.
- Probar el ciclo con un `FakeLLMProvider`, un cliente falso de WhatsApp y SQLite
  temporal.

## Requisitos funcionales

### RF-301 - Contrato independiente

El codigo consumidor debe depender del protocolo `LLMProvider` y no de una
clase especifica de Groq.

### RF-302 - Configuracion externa

El adaptador debe leer `LLM_PROVIDER`, las credenciales y los modelos del proveedor
seleccionado (`GROQ_API_KEY`/`GROQ_MODEL`, `OPENAI_API_KEY`/`OPENAI_MODEL` o
`OPENROUTER_API_KEY`/`OPENROUTER_MODEL`), sus URLs opcionales y
`LLM_TIMEOUT_SECONDS`, `LLM_MAX_HISTORY_MESSAGES`, `LLM_MAX_OUTPUT_TOKENS`,
`LLM_MAX_RESPONSE_CHARACTERS` y `LLM_MAX_TOOL_ITERATIONS`. Las URLs oficiales se
usan por defecto. Las variables genericas `LLM_API_KEY`, `LLM_MODEL` y
`LLM_BASE_URL` se admiten como fallback para el proveedor activo; la URL generica
se aplica a Groq y OpenRouter, mientras OpenAI usa su URL oficial o
`OPENAI_BASE_URL`. Si se configuran variables por proveedor, estas tienen
precedencia sobre `LLM_API_KEY` y `LLM_MODEL`.

### RF-303 - Solicitud al proveedor

El adaptador debe enviar los mensajes al endpoint seleccionado: OpenAI usa
`/responses` y Groq/OpenRouter usan `/chat/completions`. Las solicitudes usan
autenticacion Bearer, el modelo configurado y el limite de salida. OpenAI usa
`max_output_tokens`; Groq y OpenRouter usan `max_tokens`. El ID del modelo se
envia sin transformacion y debe admitir el endpoint y las herramientas de llamada
a funciones que usa el adaptador.

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

### RF-315 - Fechas relativas de agenda

El contexto del LLM debe incluir la fecha y hora actuales del backend, la zona
horaria de la agenda y los rangos ISO de hoy, manana y ayer. Cuando el paciente
use una expresion relativa, el asistente debe resolverla con ese contexto y no
pedir la fecha exacta.

### RF-308 - Ciclo de respuesta

`ConversationService` debe recuperar el historial, construir los mensajes del
LLM y solicitar la respuesta mediante `LLMProvider.generate()`. `main.py` debe
coordinar el servicio, `WhatsAppClient` y el registro de la respuesta, sin
contener reglas de conversacion.

### RF-309 - Fallos de generacion

Si el LLM no genera una respuesta, el backend debe registrar el fallo y enviar
la respuesta controlada, excepto para remitentes de depuracion autorizados segun
la especificacion 015. Si WhatsApp tambien falla, debe registrar esa salida como
`failed` y permitir reintentar el mensaje entrante posteriormente.

Segun el incremento 018, ese reintento reutiliza la respuesta preparada cuando
el turno sigue vigente. No vuelve a generar ni a ejecutar herramientas; los
turnos obsoletos o con resultado incierto se reconocen sin reenviar al paciente.

### RF-316 - Diagnostico seguro de errores HTTP

Cuando el proveedor LLM responda con un error HTTP, el backend debe guardar su codigo
en `llm_failures.http_status_code` junto con el tipo de excepcion. Los fallos que no
tengan codigo HTTP guardan `NULL`. El log operativo puede registrar el tipo y el codigo,
pero no el contenido del mensaje, credenciales ni la respuesta del proveedor. La columna
debe agregarse de forma compatible a las bases existentes.

### RF-310 - Respuesta controlada

La respuesta controlada predeterminada debe ser: `En este momento no pude procesar tu
mensaje. Intenta nuevamente en unos minutos.` El modo de depuracion autorizado y su
diagnostico limitado se definen en la especificacion 015.

### RF-311 - Pruebas sin API

La suite debe poder probar el agente sin API key real, Internet ni envio de
mensajes reales. `FakeLLMProvider` debe registrar las solicitudes y permitir
simular una respuesta o un `LLMProviderError`.

### RF-312 - Idempotencia de la respuesta

Un webhook duplicado cuyo mensaje ya tenga una respuesta `sent` no debe volver a
invocar el LLM ni enviar otra respuesta.

### RF-313 - Verificacion de Meta

La verificacion correcta de Meta debe responder el challenge con HTTP 200 sin
necesitar configurar un proveedor LLM real.

### RF-314 - Respuesta de herramienta

El contrato del proveedor debe poder representar una solicitud de herramienta con
un nombre y un objeto de argumentos sin convertirla en texto conversacional. La
normalizacion y el limite de este contrato se detallan en la especificacion 006.

## Criterios de aceptacion

1. Una configuracion valida crea el adaptador para Groq.
2. Una configuracion sin la API key o el modelo del proveedor seleccionado es rechazada.
3. Los limites opcionales usan los valores definidos para esta etapa.
4. Los requests incluyen modelo, mensajes y el parametro de limite de salida
   propio del proveedor.
5. La respuesta del proveedor se devuelve como texto limpio.
6. Un error HTTP se expone como `LLMProviderError`.
7. Las pruebas usan un transporte HTTP simulado y no requieren API key real.
8. Una configuracion valida para OpenRouter usa el mismo adaptador y endpoint.
9. El contexto recupera el historial guardado y conserva el orden de sus roles.
10. El contexto empieza con las reglas del mensaje `system` definidas para el MVP.
11. El contexto solo usa los mensajes mas recientes dentro del limite configurado.
12. El contexto temporal usa el reloj y la zona horaria del ejecutor de agenda.
13. Una solicitud que use "hoy" recibe un rango de inicio y fin de ese dia en el
    contexto del sistema.
14. Un mensaje valido genera la respuesta mediante el proveedor, la envia por
    WhatsApp y la registra como `sent`.
15. Una API key ausente, un timeout, un error HTTP, una respuesta vacia o una
    respuesta demasiado larga registran el tipo de fallo en SQLite.
16. Un fallo del LLM envia la respuesta controlada, salvo el diagnostico autorizado de
    la especificacion 015, y la registra como `sent` si WhatsApp esta disponible.
17. El `FakeLLMProvider` recibe el historial convertido y el mensaje actual como
    el ultimo mensaje `user`.
18. Una respuesta generada por el fake se envia por WhatsApp y queda guardada
    como `sent`.
19. Un webhook duplicado no incrementa las llamadas al LLM despues de una
    respuesta enviada.
20. La suite cubre errores del LLM y la verificacion de Meta sin usar servicios
    externos.
21. Un `LLMHTTPError(429)` deja el codigo `429` en SQLite y en el log operativo sin
    incluir el texto entrante; otros errores LLM mantienen el codigo HTTP en `NULL`.
22. La inicializacion agrega la columna nullable a una base existente sin perder sus
    fallos LLM ya guardados.
23. El diagnostico de errores de depuracion sigue el modo y la lista de remitentes de la
    especificacion 015 y no registra el contenido del proveedor.
24. Con las credenciales y modelos de Groq y OpenAI configurados, cambiar solo
    `LLM_PROVIDER` selecciona el par correspondiente.
25. OpenAI usa su URL oficial por defecto y no toma por error el endpoint generico
    configurado para Groq.
26. OpenAI usa Responses API, `max_output_tokens` y normaliza tool calls nativos.
27. Sin variables especificas, OpenAI acepta `LLM_API_KEY` y `LLM_MODEL` como los
    valores del proveedor activo.
28. La configuracion documenta los endpoints y los IDs admitidos por cada proveedor;
    el adaptador no transforma nombres especificos de otro proveedor.
29. Las llamadas de herramientas de Responses API conservan los elementos de salida
    necesarios, incluidos los de razonamiento, al enviar el resultado de la herramienta.

## Fuera de alcance

- Colas y procesamiento asincrono externo.
- Ejecucion de herramientas, RAG y memoria semantica.
- Uso de datos reales de pacientes.
