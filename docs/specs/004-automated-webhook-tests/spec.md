# 004 - Pruebas automatizadas del ciclo sin API

## Estado

Verificado con la suite automatica ejecutada sin credenciales ni llamadas a
servicios externos.

## Problema

El ciclo integrado de conversacion, LLM, WhatsApp y persistencia necesita una
forma repetible de verificarse sin consumir cuota, depender de Internet o enviar
mensajes reales.

## Objetivo

Probar el comportamiento observable del webhook con un proveedor LLM falso que
registre las solicitudes y permita simular errores.

## Alcance

- Agregar `FakeLLMProvider` como soporte exclusivo de pruebas.
- Registrar los mensajes recibidos por el fake y su cantidad de invocaciones.
- Permitir que el fake devuelva una respuesta conocida o lance un error LLM.
- Probar el ciclo HTTP con `TestClient`, WhatsApp falso y SQLite temporal.
- Mantener la verificacion de Meta cubierta por la suite.

## Requisitos funcionales

### RF-401 - Proveedor LLM falso

El fake debe cumplir el protocolo `LLMProvider`, no hacer llamadas de red y
conservar cada secuencia de `ChatMessage` que reciba.

### RF-402 - Mensaje actual y contexto

El flujo debe transformar el historial persistido a mensajes del modelo y enviar
el mensaje entrante actual como el ultimo mensaje `user`.

### RF-403 - Entrega y persistencia

La respuesta del fake debe enviarse mediante el cliente falso de WhatsApp y
quedar guardada como `sent`.

### RF-404 - Idempotencia despues de entregar

Un webhook duplicado cuyo mensaje ya tiene una respuesta `sent` no debe volver a
invocar el LLM ni enviar otra respuesta.

### RF-405 - Fallos del LLM

Un error del proveedor debe registrarse en SQLite y producir la respuesta
controlada, que se guarda como `sent` si WhatsApp esta disponible.

### RF-406 - Verificacion de Meta

La verificacion correcta de Meta debe continuar respondiendo el challenge aunque
no se configure ningun proveedor LLM real.

## Criterios de aceptacion

1. El fake registra el historial y el mensaje actual en el orden esperado.
2. Una respuesta del fake se envia al destinatario de WhatsApp de prueba.
3. La respuesta enviada queda persistida con estado `sent`.
4. Un webhook repetido no incrementa el numero de llamadas al fake despues de la
   primera respuesta enviada.
5. Un error simulado del LLM queda registrado en `llm_failures`.
6. La verificacion de Meta responde el challenge con estado HTTP 200.
7. La suite completa pasa sin API key de LLM, token de WhatsApp ni conexion a
   Internet.

## Fuera de alcance

- Validar el comportamiento de un modelo real.
- Enviar mensajes a WhatsApp Cloud API durante la suite.
- Probar credenciales reales o disponibilidad de servicios externos.
- Cambiar el contrato o el adaptador de proveedores LLM.
