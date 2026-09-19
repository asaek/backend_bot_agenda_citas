# WhatsApp Chatbot

Etapa 4: agente LLM basico con un contrato independiente del proveedor,
persistencia conversacional y pruebas sin consumir API mediante un
`FakeLLMProvider`.

## 1. Instalar dependencias

```bash
uv sync
```

## 2. Configurar variables de entorno

El archivo `.env` se carga automaticamente desde la raiz del proyecto y esta
excluido de Git. Usa `.env.example` como referencia y reemplaza sus valores por
los reales. El Verify Token debe coincidir con el configurado en Meta.

Las variables exportadas en la shell tienen prioridad sobre `.env`.

`DATABASE_PATH` define la ruta de la base SQLite. Si no se configura, se usa
`data/chatbot.sqlite3`. La carpeta `data/` esta excluida de Git.

El adaptador compatible con OpenAI usa estas variables adicionales:

- `LLM_PROVIDER=groq`
- `LLM_API_KEY`
- `LLM_MODEL`
- `LLM_BASE_URL=https://api.groq.com/openai/v1`
- `LLM_TIMEOUT_SECONDS=20`
- `LLM_MAX_HISTORY_MESSAGES=30`
- `LLM_MAX_OUTPUT_TOKENS=500`
- `LLM_MAX_RESPONSE_CHARACTERS=4000`

Para usar OpenRouter cambia `LLM_PROVIDER` a `openrouter`, `LLM_API_KEY`,
`LLM_MODEL` y `LLM_BASE_URL=https://openrouter.ai/api/v1`.

El agente actual solo genera texto y no incluye herramientas, RAG ni memoria
semantica. La suite automatizada usa un proveedor falso y no requiere estas
credenciales.

El corte activo define el modelo de dominio, los contratos tipados de las cinco
herramientas, la validacion previa al proveedor, los errores publicos,
`CalendarProvider`, `FakeCalendarProvider` y `ToolExecutor`. La conexion a
Google Calendar queda pendiente.

El webhook crea el proveedor, recupera el historial desde `ConversationService`,
genera la respuesta, la envia por WhatsApp y registra el resultado. Un fallo de
generacion o envio queda marcado como `failed` para permitir un reintento.

## 3. Iniciar el servidor

```bash
uv run uvicorn main:app --reload
```

El backend queda disponible en <http://127.0.0.1:8000>.

## 4. Probar localmente

En otra terminal, comprueba el estado del backend:

```bash
curl http://127.0.0.1:8000/
```

Simula la verificacion que realizara Meta:

```bash
curl "http://127.0.0.1:8000/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=mi-token-secreto&hub.challenge=12345"
```

La respuesta debe ser `12345`.

Simula un evento entrante de WhatsApp:

```bash
curl -X POST http://127.0.0.1:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{"object":"whatsapp_business_account","entry":[{"changes":[{"value":{"messages":[{"from":"5491100000000","id":"wamid.test","type":"text","text":{"body":"Hola"}}]}}]}]}'
```

La respuesta debe ser `{"status":"ok"}`. El backend extrae el remitente, el ID,
el tipo y el texto, identifica o crea el paciente de prueba, construye el
contexto, genera la respuesta, la envia y la guarda como `sent`.

Un segundo evento con el mismo valor de `from` reutiliza el paciente y la
conversacion activa. Si Meta reenvia el mismo `id`, el backend no duplica la
respuesta cuando ya fue enviada.

Para probar persistencia, continuidad, idempotencia y la construccion de la
solicitud de salida sin enviar un mensaje real ni consumir un LLM:

```bash
uv run python -m unittest discover -s tests -v
```

La suite usa un proveedor LLM falso, un cliente falso de WhatsApp y una base
SQLite temporal. Tambien verifica la transformacion del historial, el mensaje
actual, las respuestas `sent`, los errores del LLM, los webhooks duplicados y la
verificacion de Meta.

## Endpoints

- `GET /`: comprobacion sencilla del servidor.
- `GET /webhook/whatsapp`: verificacion solicitada por Meta.
- `POST /webhook/whatsapp`: recepcion de eventos enviados por Meta, persistencia
  de mensajes y respuesta generada por el LLM para mensajes de texto.

Los eventos que no sean mensajes de texto, como estados, imagenes o audios, se
ignoran temporalmente. Las credenciales solo deben existir como variables de
entorno en la Raspberry Pi:

- `WHATSAPP_VERIFY_TOKEN`
- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`

`DATABASE_PATH` no es una credencial, pero debe apuntar a una ruta persistente en
la Raspberry Pi.
