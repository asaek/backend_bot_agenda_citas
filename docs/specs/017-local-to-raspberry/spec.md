# 017 - Espejo de proyecto y configuracion en Raspberry Pi

## Estado

Verificado en el mirror Raspberry Pi. El usuario solicito que `local to raspberry`
copie tambien el `.env` completo del checkout local como parte del flujo habitual.
Evidencia en `docs/verification/2026-10-08-local-to-raspberry-full-env.md`.

## Objetivo

Que el backend de Raspberry Pi ejecute el proyecto y la configuracion locales,
evitando que un despliegue aparentemente correcto siga usando credenciales antiguas.

## Requisitos

### RF-1701 - Configuracion incluida por defecto

Una solicitud `local to raspberry` sincroniza los archivos del proyecto y reemplaza
el `.env` de la Pi con el archivo local completo. Incluye todas las claves,
comentarios y formato; no realiza una mezcla de configuraciones. La solicitud ya
autoriza esa copia y no requiere una confirmacion adicional por el archivo.

### RF-1702 - Comprobacion de la copia

El `.env` remoto debe coincidir byte por byte con el local y tener modo `600`.
La comprobacion se realiza en memoria y muestra solo coincidencia y permisos.
Un `.env` local ausente o una copia fallida bloquean la finalizacion del flujo.

### RF-1703 - Reinicio y configuracion efectiva

Tras sincronizar se reinicia el backend verificado, aunque el codigo no cambie.
Se comprueban el proceso o servicio, directorio, puerto y uso de los valores
actualizados de `.env`, sin heredar configuracion exportada antigua.

### RF-1704 - Verificacion de rutas y autenticacion

El health check y ambos metodos del webhook local y publico deben responder HTTP
200 con el cuerpo esperado. Si esta configurado el envio de WhatsApp, una consulta
autenticada de solo lectura a Meta tambien debe pasar: un webhook saludable no
demuestra que la credencial de envio sea valida.

### RF-1705 - Alcances explicitos

Una solicitud que excluya `.env` conserva ese archivo. Si solicita solo una variable,
se actualiza exclusivamente esa clave. Una sincronizacion expresamente sin reinicio
sigue comprobando la copia, pero omite la recarga. Un reinicio aislado usa la
configuracion ya presente en la Pi. Una ruta de codigo limitada conserva su alcance,
con `.env` incluido por defecto en la solicitud de despliegue.

### RF-1706 - Confidencialidad y espejo

La transferencia utiliza SSH. Los valores no aparecen en argumentos de comandos,
salida, logs, huellas ni documentos, y `.env` permanece excluido de Git. El codigo
y la documentacion se editan localmente; el paso de configuracion es la unica
escritura remota autorizada sobre `.env`. Se conservan los datos y archivos exclusivos
de la Pi que no pertenecen al alcance de la sincronizacion.

## Criterios de aceptacion

1. Un `local to raspberry` ordinario copia `.env` completo sin una pregunta adicional.
2. Un archivo remoto inicialmente diferente termina identico al local y con modo `600`.
3. Una sincronizacion con codigo sin cambios tambien copia la configuracion y reinicia.
4. El proceso nuevo usa los valores actualizados y posee el puerto esperado.
5. Las rutas y la comprobacion de autenticacion de Meta pasan sin mostrar secretos.
6. La skill, `AGENTS.md` y README describen el mismo flujo y sus alcances explicitos.

## Fuera del alcance

- Generar o renovar credenciales en los proveedores.
- Enviar mensajes reales o repetir solicitudes de agenda durante una sincronizacion.
- Convertir el mirror del MVP en un despliegue de produccion.
