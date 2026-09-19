# Arquitectura

## Estado

Borrador evolutivo.

## Arquitectura actual

```text
WhatsApp
    |
    v
WhatsApp Cloud API
    |
    v
ngrok
    |
    v
FastAPI + Uvicorn
    |
    v
FastAPI parsea mensajes de texto
    |
    v
Conversation Service
    |
    +-- Repositories -> SQLite
    |
    v
WhatsAppClient -> WhatsApp Cloud API
```

Durante el desarrollo local, ngrok proporcionara la URL publica que Meta
necesita para comunicarse con FastAPI.

## Arquitectura objetivo

```text
WhatsApp
    |
    v
Webhook
    |
    v
Python Backend
    |
    +-- Conversation Service
    |
    v
AI Agent
    +-- LLM
    +-- Memory
    +-- RAG
    +-- Tools
          +-- Database
          +-- External APIs
          +-- n8n
    |
    v
WhatsApp Cloud API
    |
    v
Usuario
```

Esta arquitectura representa una direccion, no componentes que deban crearse
desde el inicio.

## Responsabilidades actuales

### WhatsApp Cloud API

Entrega eventos al webhook y permite enviar mensajes a WhatsApp.

### ngrok

Expone temporalmente el servidor local mediante una URL HTTPS publica. No forma
parte de la arquitectura de produccion.

### FastAPI

Define los endpoints HTTP y transforma las solicitudes en llamadas al codigo del
backend. Extrae mensajes de texto y coordina el `ConversationService`.

### Conversation Service

Identifica al paciente de prueba por su numero de WhatsApp, busca o crea una
conversacion activa, conserva el historial y construye el contexto para el LLM.
El contexto comienza con las reglas del asistente y usa los mensajes mas
recientes persistidos. Tambien solicita la respuesta al proveedor LLM y conserva
el resultado del envio.

### Persistence y repositories

`persistence.py` administra conexiones, esquema y transacciones SQLite.
`repositories.py` encapsula las operaciones de pacientes, conversaciones y
mensajes. La ruta de la base se configura mediante `DATABASE_PATH`.

### WhatsAppClient

Construye la solicitud autenticada de tipo texto para WhatsApp Cloud API usando
`WHATSAPP_ACCESS_TOKEN` y `WHATSAPP_PHONE_NUMBER_ID`. No contiene logica de
conversacion.

### LLMProvider

Define el contrato asincrono `generate(messages)` para que la logica
conversacional no dependa de un proveedor concreto. El adaptador
`OpenAICompatibleLLMProvider` usa `httpx` y variables de entorno para Groq u
OpenRouter.

El adaptador participa en el flujo del webhook mediante la inyeccion de
`LLMProvider` en `ConversationService`. `main.py` coordina la generacion, el
envio y el registro, pero no decide el contenido conversacional.

### Uvicorn

Ejecuta la aplicacion ASGI y gestiona las conexiones HTTP.

### Google Calendar

Sera la fuente de verdad de la agenda del medico durante el MVP tecnico. Alli se
administraran las citas, los dias no laborables y los espacios bloqueados
manualmente. El backend lo consultara y modificara mediante herramientas
controladas; el LLM no recibira credenciales ni acceso directo al calendario.

Cada cita creada por el chatbot ocupara 30 minutos. Antes de ofrecer o reservar
un horario, el backend debera comprobar tanto que el espacio no este ocupado
como que pertenezca al horario de atencion configurado.

La integracion se realizara sobre calendarios que ya estan en uso y contienen
eventos anteriores. El backend debera conservar esos eventos y no podra
eliminarlos, reemplazarlos ni reinterpretarlos sin una regla explicita. Para
calcular disponibilidad debera combinar:

- Horario laboral del medico.
- Citas existentes.
- Dias festivos o no laborables.
- Ausencias del medico.
- Espacios bloqueados manualmente.

Antes de implementar la integracion se documentara como identificar cada clase
de evento en los calendarios actuales.

La API de Google Calendar puede consultar los periodos ocupados de uno o varios
calendarios. Tambien expone algunos tipos especiales, como eventos de fuera de
oficina, pero los eventos normales no indican automaticamente si representan
una cita medica, un bloqueo o una actividad personal. Por ello, la disponibilidad
tratara todos los periodos ocupados de los calendarios seleccionados como no
disponibles, sin importar su titulo o categoria y sin necesitar interpretar su
contenido.

Los eventos nuevos creados por el chatbot podran llevar propiedades extendidas
privadas para identificarlos como citas administradas por el sistema. Los
eventos existentes no tendran esos metadatos salvo que se hayan añadido
previamente, por lo que primero se inspeccionara su estructura en modo de solo
lectura.

Referencias oficiales:

- [Consulta de disponibilidad](https://developers.google.com/workspace/calendar/api/v3/reference/freebusy/query)
- [Tipos de evento](https://developers.google.com/workspace/calendar/api/v3/reference/events)
- [Propiedades extendidas](https://developers.google.com/workspace/calendar/api/guides/extended-properties)

## Flujo futuro de una herramienta de agenda

```text
Mensaje del paciente de prueba
    |
    v
LLM solicita una herramienta
    |
    v
Backend valida la solicitud
    |
    v
Google Calendar
    |
    v
Resultado de la herramienta
    |
    v
LLM redacta la respuesta
```

## Limites actuales

- El backend solo mantiene estado conversacional basico.
- La respuesta sigue siendo un texto fijo de prueba; el adaptador LLM aun no esta
  conectado al webhook.
- El contexto usa una ventana acotada del historial y no incluye respuestas de
  WhatsApp registradas como fallidas.
- SQLite se usa para una unica instalacion del MVP y no para multiples replicas.
- Los secretos se proporcionan mediante variables de entorno y no se guardan
  en el repositorio.

## Preguntas abiertas

- ¿Donde se desplegara inicialmente el backend de produccion?
- ¿Se procesaran los eventos dentro de la solicitud o mediante una cola cuando
  aumente el volumen?
- ¿Que proveedor de LLM se utilizara en la primera integracion?
