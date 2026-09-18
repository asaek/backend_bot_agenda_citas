# 002 - Persistencia y Conversation Service

## Estado

Verificado en la Raspberry Pi con recepcion, persistencia y respuesta real de
WhatsApp Cloud API.

## Problema

El webhook actual procesa cada mensaje de forma aislada y responde con un texto
fijo sin guardar informacion. Si el proceso se reinicia, el backend no puede
reconocer al mismo paciente de prueba ni continuar una conversacion anterior.

## Objetivo

Guardar pacientes de prueba, conversaciones y mensajes para que una conversacion
pueda continuar despues de varias solicitudes y de un reinicio del backend.

## Alcance

Esta etapa agrega persistencia local y un `ConversationService` que coordina la
identificacion del paciente, la conversacion activa, el historial y la respuesta
automatica existente. La respuesta sigue siendo fija y determinista.

Durante el MVP tecnico, el numero de WhatsApp recibido en `from` identifica a un
unico paciente de prueba. Si el numero no existe, el backend crea el registro.
Esta identificacion no representa autenticacion de pacientes reales.

## Requisitos funcionales

### RF-201 - Persistencia local

El backend debe guardar la informacion en una base SQLite configurada mediante
`DATABASE_PATH`. La base debe conservar los datos despues de reiniciar el
proceso.

### RF-202 - Identificacion del paciente de prueba

Para cada mensaje de texto valido, el backend debe buscar el paciente por su
numero de WhatsApp y crear el registro si no existe.

### RF-203 - Conversacion activa

El backend debe buscar o crear una conversacion activa para el paciente. Un
paciente debe tener como maximo una conversacion activa en esta etapa.

### RF-204 - Persistencia de mensajes

El backend debe guardar cada mensaje entrante y cada respuesta saliente asociada
con su conversacion, direccion, texto, tipo, estado y fecha en UTC.

### RF-205 - Respuesta mediante Conversation Service

La respuesta automatica debe ser decidida por `ConversationService`, que en esta
etapa devolvera la respuesta fija existente. `main.py` no debe contener la
logica de decision conversacional.

### RF-206 - Continuidad conversacional

Mensajes posteriores del mismo numero deben reutilizar el mismo paciente y la
misma conversacion activa. El historial debe poder recuperarse mediante el
servicio.

### RF-207 - Idempotencia de eventos

Un mensaje entrante identificado por un `provider_message_id` ya procesado no
debe crear registros duplicados ni enviar una segunda respuesta si la respuesta
anterior ya fue enviada.

### RF-208 - Registro de fallos de salida

Si el envio mediante WhatsApp falla, el backend debe conservar el mensaje
entrante y registrar la respuesta saliente como fallida para permitir un reintento
posterior.

### RF-209 - Eventos no soportados

Los eventos de estado y los mensajes que no sean de tipo `text` deben seguir
respondiendo exitosamente sin crear pacientes, conversaciones ni mensajes.

## Criterios de aceptacion

1. El primer mensaje de texto de un numero crea un paciente de prueba.
2. El primer mensaje de texto de un numero crea una conversacion activa.
3. El mensaje entrante queda guardado antes de intentar enviar la respuesta.
4. Una respuesta enviada correctamente queda guardada como `sent`.
5. Un segundo mensaje del mismo numero reutiliza el paciente y la conversacion.
6. El historial recuperado contiene los mensajes entrantes y salientes en orden.
7. Dos numeros distintos generan pacientes y conversaciones independientes.
8. Repetir exactamente el mismo webhook no duplica mensajes ni respuestas.
9. Un fallo de WhatsApp queda guardado como `failed` y permite reintentar.
10. Un reinicio del servicio conserva el paciente, la conversacion y el historial.
11. Los eventos de estado y los mensajes no textuales siguen sin crear datos.

## Fuera de alcance

- LLM, agentes, tool calling o RAG.
- Memoria semantica o resumen automatico.
- Redis, colas o procesamiento asincrono externo.
- PostgreSQL y pgvector.
- Google Calendar y gestion de citas.
- Autenticacion de pacientes reales.
- Procesamiento de imagenes, audio, documentos o ubicaciones.

## Preguntas abiertas

- ¿Cuando debe cerrarse una conversacion activa?
- ¿Que politica de retencion y eliminacion se aplicara antes de usar datos reales?
