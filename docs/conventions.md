# Convenciones

## Estado

Borrador.

## Documentacion

- Cada funcionalidad nueva debe comenzar con una carpeta dentro de `specs/`.
- Las especificaciones usan numeros consecutivos de tres digitos.
- Las decisiones arquitectonicas usan numeros consecutivos de cuatro digitos.
- Los documentos deben indicar claramente su estado.
- Los requisitos deben poder verificarse de forma objetiva.

## Logica conversacional en ambos canales

Regla vigente, adoptada por indicacion del usuario el 28/10/2026.

Las formas de conversar con el asistente se denominan **canales**: **canal de
voz** y **canal de texto**, segun el glosario de `CONTEXT.md`.

Todo cambio de logica conversacional debe implementarse y verificarse en ambos
canales dentro del mismo cambio. Esto incluye correcciones de errores y cambios
de intencion, secuencia de preguntas, disponibilidad, captura de nombre/motivo,
validaciones, aclaraciones, reintentos y confirmaciones, incluidos los prompts
que gobiernan esas decisiones.

### Criterios de completitud

1. Identificar las rutas afectadas de ambos canales. El canal de texto incluye
   WhatsApp y los mensajes de laboratorio; el canal de voz incluye las llamadas
   de laboratorio y su futura integracion operativa.
2. Aplicar la regla en la logica compartida cuando exista y comprobar sus
   adaptadores; actualizar tambien las rutas especificas que resuelvan esa
   decision por separado.
3. Verificar el comportamiento equivalente en ambos canales. Una correccion de
   un incidente debe cubrir el escenario de regresion en voz y en texto.
4. Conservar las reglas de autorizacion, entrega y presentacion propias de cada
   canal al aplicar la misma decision conversacional.
5. Actualizar la SDD y registrar la evidencia de ambos canales. La tarea se
   considera completa cuando el cambio esta aplicado y verificado en los dos.

## Codigo

- Python 3.12 o superior.
- Dependencias y entorno virtual administrados con `uv`.
- Endpoints HTTP definidos con FastAPI.
- Aplicacion ejecutada localmente con Uvicorn.
- Las funciones y variables del codigo se nombran en ingles.
- Los comentarios explican decisiones, no repiten el codigo.

## Configuracion y secretos

- Los secretos se proporcionan mediante variables de entorno.
- Los archivos `.env` no se guardan en Git.
- La aplicacion carga `.env` desde la raiz del proyecto al iniciar; las variables
  exportadas explicitamente tienen prioridad.
- `WHATSAPP_VERIFY_TOKEN` contiene el token elegido para verificar el webhook.
- El Verify Token y el Access Token de WhatsApp son credenciales diferentes.
- La configuracion de WhatsApp del runtime se conserva en el `.env` local y se
  copia al mirror de Raspberry Pi mediante el flujo de `specs/017-local-to-raspberry/`.
  Los valores quedan fuera de Git, argumentos, logs y documentacion.

## Implementacion incremental

- No se agrega una tecnologia hasta que exista una necesidad concreta.
- No se introduce una abstraccion para un unico caso sin una razon demostrable.
- Cada tarea se verifica antes de comenzar la siguiente etapa.

## Preguntas abiertas

- ¿El codigo, los commits y la documentacion se escribiran en español o ingles?
- ¿Que herramienta de pruebas y que reglas de formato se adoptaran?
- ¿Que convencion se utilizara para los mensajes de commit?
