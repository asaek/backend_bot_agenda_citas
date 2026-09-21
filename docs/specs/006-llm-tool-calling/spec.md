# 006 - Contrato de tool calling del LLM

## Estado

Implementado y verificado para la normalizacion de respuestas. La ejecucion
orquestada se define en la especificacion 007.

## Problema

`LLMProvider` solo devuelve texto, por lo que el modelo no puede expresar de
forma estructurada que necesita una operacion del backend.

## Objetivo

Ampliar el contrato del proveedor para representar una respuesta textual o una
solicitud de herramienta con nombre y argumentos, sin permitir que esa solicitud
elija el paciente o la conversacion.

## Alcance

- Definir `ToolCall` como respuesta no confiable del LLM.
- Definir `LLMResponse` como texto o `ToolCall`.
- Normalizar tool calls nativos de proveedores compatibles con OpenAI.
- Aceptar una forma interna `tool_call` con `name` y `arguments` objeto.
- Validar nombres no vacios y argumentos JSON de tipo objeto.
- Mantener el flujo textual existente.
- Enviar al proveedor los esquemas OpenAI-compatible de las herramientas.
- Entregar tool calls al orquestador sin enviarlos como texto a WhatsApp.
- Probar todo sin API ni proveedor externo.

## Requisitos funcionales

### RF-601 - Respuesta textual

Una respuesta con contenido textual debe continuar devolviendo una cadena
recortada y respetar el limite de caracteres configurado.

### RF-602 - Respuesta de herramienta

Una respuesta de herramienta debe devolver un `ToolCall` con `name` y un mapa de
`arguments`. Los argumentos no se validan como contrato de agenda en esta capa.

### RF-603 - Formato compatible

El adaptador debe traducir `message.tool_calls[0].function.name` y sus argumentos
JSON al `ToolCall` interno. Tambien debe aceptar la forma normalizada
`message.tool_call` para dobles y adaptadores internos.

### RF-604 - Validacion de respuesta

El adaptador debe rechazar nombres vacios, argumentos que no sean objetos,
JSON invalido y respuestas con mas de una herramienta.

### RF-605 - Limite de seguridad

Un `ToolCall` no debe enviarse directamente como texto al paciente. Hasta que el
ejecutor se integre, el webhook debe registrar el tipo de respuesta y enviar la
respuesta controlada existente.

### RF-606 - Alcance backend

`ToolCall` no contiene `patient_id`, `conversation_id` ni `whatsapp_number` como
campos de identidad. El backend resolvera `PatientScope` desde WhatsApp cuando
construya el `ToolRequest` en un incremento posterior.

### RF-607 - Esquema de herramientas

El adaptador OpenAI-compatible debe enviar las cinco herramientas del backend con
sus nombres, descripciones, argumentos requeridos y `additionalProperties=false`.
El esquema no debe incluir campos de identidad, calendario ni duracion controlados
por el backend.

## Criterios de aceptacion

1. El proveedor sigue devolviendo texto para respuestas textuales existentes.
2. Una respuesta nativa de OpenAI con una herramienta produce `ToolCall`.
3. La forma `tool_call` produce el mismo tipo normalizado.
4. Los argumentos se conservan como objeto y no como JSON serializado.
5. Un nombre o argumento invalido produce `LLMResponseError`.
6. Mas de una herramienta produce `LLMResponseError`.
7. El fake puede devolver texto, `ToolCall` o un error.
8. Un webhook con `ToolCall` no envia la representacion del objeto por WhatsApp.
9. Los identificadores de paciente no se solicitan al LLM.
10. La suite pasa sin credenciales ni llamadas externas.

## Fuera de alcance

- Persistir resultados de herramientas.
- Construir el bucle tool call -> resultado -> LLM.
- Ejecutar herramientas sin el orquestador.
- Integrar Google Calendar.
