# Diseno - Espejo de proyecto y configuracion en Raspberry Pi

## Estado

Implementado mediante instrucciones operativas de la skill y `AGENTS.md`.

## Flujo

`Archivos del proyecto -> .env completo -> comparacion en memoria -> reinicio -> HTTP y Meta`.

La skill `.agents/skills/local-to-raspberry/SKILL.md` contiene los pasos ejecutables.
`AGENTS.md` fija el destino y autoriza la copia completa como alcance por defecto.

La sincronizacion masiva conserva la exclusion de `.env` para tratar ese archivo
en un paso obligatorio dedicado, con `rsync` sobre SSH, `--ignore-times` y
`--chmod=u=rw,go=` (modo `600`, compatible con openrsync de macOS y GNU rsync).
La copia se realiza incluso si tamano y timestamp coinciden;
reemplaza el archivo en vez de mezclar claves. La comparacion posterior envia el
contenido local por entrada estandar de SSH y compara bytes en memoria con el
archivo de la Pi, sin publicar contenidos ni hashes.

Para un alcance explicito de una variable se mantiene `python-dotenv.set_key()`.
El reinicio carga la configuracion fresca desde la raiz del mirror y comprueba
coincidencia de los valores efectivos en memoria. El caso manual puede proporcionar
al proceso los valores recien leidos, limpiando primero las claves gestionadas.

Los POST de verificacion usan eventos vacios. La comprobacion de credenciales usa
una consulta GET de Meta con `fields=id` y autenticacion en memoria; reporta solo
HTTP y codigos seguros de error. Ninguna de estas comprobaciones envia mensajes.

La implementacion cambia instrucciones operativas, no el codigo del chatbot ni
sus contratos. La verificacion significativa consiste en ejecutar el flujo real
contra el mirror y comprobar archivos, permisos, proceso y respuestas.
