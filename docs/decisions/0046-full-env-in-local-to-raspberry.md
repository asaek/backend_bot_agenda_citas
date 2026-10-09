# ADR 0046 - Copiar .env completo en local to raspberry

## Estado

Aceptada. Adoptada por la skill del proyecto y `AGENTS.md`.

## Contexto y decision

El flujo anterior excluia `.env` de un despliegue general y requeria pedir aparte
la transferencia de configuracion. Una sincronizacion con webhooks saludables
podia seguir usando un token vencido de WhatsApp, aunque el local fuera vigente.
El usuario solicito que el archivo tambien forme parte del espejo habitual.

`local to raspberry` autoriza por defecto reemplazar el `.env` remoto con el local
completo, verificar igualdad byte por byte y modo `600`, y reiniciar con los valores
frescos. La copia dedicada evita publicar secretos y aplica los permisos correctos.
La autenticacion de Meta de solo lectura complementa los checks del webhook.

La configuracion local es la fuente del archivo completo, incluidas claves retiradas;
una mezcla silenciosa conservaria ajustes remotos inesperados. El alcance explicito
de una variable conserva las demas claves, y una exclusion explicita de `.env` lo
deja intacto. Los secretos permanecen fuera de Git, argumentos, logs y documentacion.
