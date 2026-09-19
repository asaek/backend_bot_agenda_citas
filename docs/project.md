# Definicion del proyecto

## Estado

Borrador.

## Objetivo

Construir progresivamente un chatbot de WhatsApp con inteligencia artificial,
entendiendo y controlando cada capa de la arquitectura desde un backend propio.
El caso de uso objetivo es gestionar citas medicas con un oftalmologo
especialista en cornea.

## Enfoque

El proyecto comenzara con la recepcion y el envio de mensajes de WhatsApp. Las
capacidades de persistencia, inteligencia artificial, memoria, herramientas y
RAG se agregaran solamente cuando la etapa anterior este comprendida y
verificada.

La primera version sera un MVP tecnico para aprendizaje y experimentacion. No
sera utilizada todavia por pacientes ni por un consultorio real.

## Usuarios del MVP tecnico

El desarrollador administrara las pruebas y utilizara varias cuentas de
WhatsApp como clientes simulados. Esto permitira observar el comportamiento del
chatbot con distintas conversaciones e identidades sin involucrar todavia a
pacientes ni clientes reales.

Cada cuenta representara un perfil de paciente de prueba. Estos perfiles podran
usar informacion ficticia o datos personales del propio desarrollador
proporcionados voluntariamente para las pruebas. No se utilizaran datos de
terceros ni de pacientes reales durante el MVP tecnico.

Cada numero de WhatsApp identificara a un solo paciente de prueba. Durante el
MVP, un paciente no podra gestionar citas para familiares u otras personas.

## Alcance actual

- Ejecutar un backend local con Python y FastAPI.
- Verificar una Callback URL con Meta.
- Recibir un evento de WhatsApp en `POST /webhook/whatsapp`.
- Parsear mensajes de texto y enviar una respuesta generada por el LLM.
- Identificar pacientes de prueba por su numero de WhatsApp.
- Guardar pacientes, conversaciones y mensajes en SQLite.
- Mantener una conversacion activa entre varias solicitudes y reinicios.
- Construir el contexto de chat desde el historial reciente y las reglas del
  asistente.
- Integrar el LLM en el ciclo de respuesta y conservar los fallos en SQLite.

## Estrategia de implementacion por cortes

El proyecto se construira y verificara una seccion a la vez. No se comenzara un
corte nuevo hasta cerrar el corte activo.

### Corte anterior: webhook y respuesta fija de WhatsApp

El corte termina cuando un mensaje enviado desde una cuenta de WhatsApp de prueba
llega a FastAPI, se parsea y recibe una respuesta fija. La verificacion real con
Meta y Raspberry Pi fue completada; las tareas historicas permanecen en
`specs/001-whatsapp-webhook/tasks.md`.

### Corte anterior: persistencia y Conversation Service

El objetivo es conservar pacientes, conversaciones y mensajes para que un segundo
mensaje del mismo numero reutilice el contexto basico despues de varias
solicitudes o de un reinicio. Las tareas de este corte estan en
`specs/002-persistence-conversation-service/tasks.md`.

### Corte activo: ciclo integrado de LLM y WhatsApp

Los tres primeros incrementos de la etapa 4 definen una frontera independiente
del proveedor, preparan un adaptador compatible con OpenAI para Groq y
OpenRouter, construyen el contexto desde el historial reciente e integran el
ciclo de generacion y envio. Las tareas estan en
`specs/003-llm-provider-groq/tasks.md`.

### Cortes futuros

Los siguientes temas se especificaran por separado cuando corresponda:

1. Memoria conversacional avanzada.
2. Herramientas y Google Calendar.
3. RAG con PostgreSQL y pgvector.
4. Automatizaciones externas y despliegue.

Esta lista expresa una direccion general y no autoriza su implementacion durante
el corte actual.

## Fuera del alcance actual

- Agente con tool calling y RAG.
- Integraciones con n8n.
- Redis y procesamiento mediante colas.
- PostgreSQL y pgvector.
- Despliegue de produccion.

## Flujo esperado del MVP tecnico

```text
Usuario de prueba
    |
    v
Mensaje de WhatsApp
    |
    v
Backend
    |
    v
LLM con acceso controlado a memoria y herramientas
    |
    v
Respuesta generada
    |
    v
Backend
    |
    v
Respuesta en WhatsApp
```

El MVP tecnico se considerara terminado cuando este flujo completo funcione de
extremo a extremo con las diferentes cuentas de WhatsApp utilizadas como
clientes simulados.

## Herramientas del MVP tecnico

El agente debera poder solicitar al backend las siguientes acciones:

- Consultar la disponibilidad de horarios.
- Crear una cita.
- Consultar las citas asociadas al paciente de prueba.
- Reprogramar una cita.
- Cancelar una cita.

El LLM podra decidir cuando solicitar una herramienta, pero el backend sera el
responsable de validar y ejecutar cada accion.

Las herramientas de agenda se integraran con Google Calendar. El LLM solicitara
la operacion correspondiente y el backend consultara o modificara el calendario;
el LLM no tendra acceso directo a Google Calendar.

## Informacion de una cita

Cada cita debera contener como minimo:

- Paciente de prueba.
- Fecha y hora.
- Duracion fija de 30 minutos durante el MVP tecnico.
- Motivo de la cita.
- Notas.
- Cero o mas etiquetas internas.
- Estado.

El paciente podra explicar libremente el motivo de su cita. El LLM podra
clasificar ese texto para uso interno del medico y para estadisticas. El
paciente no necesita conocer ni seleccionar esa clasificacion.

Una cita podra tener varias etiquetas internas al mismo tiempo. Las etiquetas
podran considerar, entre otros aspectos, una posible operacion, una revision
periodica, una observacion o el tipo de dolencia descrito.

Una posible urgencia se tratara como una señal de prioridad separada, no como
estado de la cita ni como diagnostico medico. Durante el MVP tecnico, esta señal
no activara un flujo especial y no impedira agendar la cita, pero debera aparecer
en el resumen de la conversacion. Antes de trabajar con pacientes reales se
debera especificar y verificar un flujo seguro de atencion para estos casos.

Los estados aceptados inicialmente son:

- `programada`
- `confirmada`
- `cancelada`
- `completada`
- `no_asistio`

## Informacion conversacional

Cuando sea necesario para completar el flujo, el sistema debera conservar:

- Nombre del paciente de prueba.
- Numero de telefono.
- Fecha preferida para la cita.
- Motivo de la cita.
- Mensajes anteriores de la conversacion, cuando existan.

La estrategia y duracion de esta memoria se definiran en una especificacion
posterior.

## Evolucion prevista

Despues de validar el MVP tecnico, el sistema evolucionara hacia la gestion de
citas medicas con un oftalmologo especialista en cornea. Antes de utilizarlo con
pacientes reales sera necesario definir requisitos de privacidad, seguridad,
consentimiento y limites para el tratamiento de informacion medica.

## Resultado general esperado

Un backend mantenible que reciba mensajes, gestione conversaciones y coordine
un agente de IA capaz de usar memoria y herramientas para asistir en la gestion
de citas.

## Preguntas abiertas

- ¿En cual de los calendarios existentes creara las citas el chatbot?
- ¿Donde se configurara el horario laboral permitido si los calendarios actuales
  no lo representan de forma explicita?
