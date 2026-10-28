# ADR 0062 - Prefijo explicito en la allowlist de depuracion WhatsApp

## Estado

Aceptada e implementada.

Complementa la [ADR 0038](./0038-debug-error-reporting.md), que conserva la decision
de limitar los diagnosticos a remitentes autorizados.

## Contexto

`DEBUG_WHATSAPP_NUMBERS` se comparaba despues de eliminar todo caracter que no fuera
digito. Como resultado, una configuracion sin el `+` E.164 era aceptada implicitamente,
lo que hacia menos visible el formato requerido y distinto de otras listas de numeros.

## Decision

Cada numero de `DEBUG_WHATSAPP_NUMBERS` debe incluir explicitamente `+` seguido de un
numero con formato E.164. El backend valida el formato antes de normalizar la entrada a
digitos para compararla con el remitente recibido desde Meta. Una entrada sin `+` o con
formato invalido no autoriza a ese numero; se ignora sin impedir que otras entradas
validas de la lista sigan funcionando.

## Consecuencias

- La configuracion debe escribirse, por ejemplo, como
  `DEBUG_WHATSAPP_NUMBERS=+5217531363338`.
- Los remitentes entrantes siguen comparandose por sus digitos; no se cambia el formato
  de envio de mensajes ni la normalizacion de los numeros del paciente.
- Una lista vacia o compuesta unicamente por entradas invalidas no revela diagnosticos.
