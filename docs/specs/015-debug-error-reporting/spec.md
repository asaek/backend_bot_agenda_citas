# 015 - Diagnostico seguro de errores en modo debug

## Estado

Verificado en Raspberry Pi.

## Problema

La respuesta generica ante fallos del backend permite recuperarse sin exponer detalles,
pero durante el MVP tecnico dificulta distinguir errores del proveedor LLM, respuestas
no manejadas y problemas de configuracion.

## Alcance

El webhook puede sustituir la respuesta generica por un diagnostico sanitizado para un
remitente de prueba expresamente autorizado. El modo no cambia la persistencia del fallo
ni las respuestas enviadas a otros remitentes.

## Requisitos funcionales

### RF-1501 - Apagado por defecto

`DEBUG_MODE` debe estar desactivado si no se configura o si su valor no es verdadero.
Con el modo apagado, el comportamiento conserva la respuesta controlada existente.

### RF-1502 - Autorizacion por remitente

Los diagnosticos solo se muestran si `DEBUG_MODE` esta activo y el numero entrante,
normalizado a digitos, coincide con una entrada de `DEBUG_WHATSAPP_NUMBERS`. La lista
acepta numeros E.164 separados por comas. Una lista vacia no autoriza a nadie.

### RF-1503 - Diagnostico limitado

La respuesta debug puede contener el nombre seguro del proveedor, el tipo de error, el
codigo HTTP cuando exista o un codigo publico de agenda. No debe mostrar el mensaje crudo
de la excepcion, cuerpos o encabezados HTTP, mensajes del paciente, prompts, argumentos
de herramientas, tokens ni otras credenciales.

### RF-1504 - Persistencia y logs existentes

El registro de errores en SQLite y el log operativo conservan el tipo y codigo HTTP
actuales. El modo debug solo cambia el texto de respuesta enviado al remitente autorizado.

## Criterios de aceptacion

1. Sin `DEBUG_MODE=true`, un error LLM sigue enviando la respuesta generica.
2. Con el modo activo, un error solo se detalla al numero incluido en la allowlist.
3. Un remitente no autorizado recibe la respuesta generica incluso si el modo esta activo.
4. Un error HTTP 429 autorizado informa proveedor, tipo de error y `HTTP=429`.
5. Una respuesta debug no contiene el texto entrante ni el mensaje crudo del error.
6. Un `ToolCall` no manejado usa el mismo limite de autorizacion.
7. La persistencia del error y el codigo HTTP no dependen del modo debug.
8. Los errores publicos de agenda muestran su codigo seguro solo al remitente autorizado.

## Fuera de alcance

- Mostrar trazas de stack, cuerpo HTTP o encabezados del proveedor.
- Cambiar cuotas, limites o reintentos del proveedor LLM.
- Exponer detalles a todos los numeros entrantes.
