# Convenciones

## Estado

Borrador.

## Documentacion

- Cada funcionalidad nueva debe comenzar con una carpeta dentro de `specs/`.
- Las especificaciones usan numeros consecutivos de tres digitos.
- Las decisiones arquitectonicas usan numeros consecutivos de cuatro digitos.
- Los documentos deben indicar claramente su estado.
- Los requisitos deben poder verificarse de forma objetiva.

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
- `WHATSAPP_ACCESS_TOKEN` y `WHATSAPP_PHONE_NUMBER_ID` solo se configuran en el
  entorno de ejecucion de la Raspberry Pi.

## Implementacion incremental

- No se agrega una tecnologia hasta que exista una necesidad concreta.
- No se introduce una abstraccion para un unico caso sin una razon demostrable.
- Cada tarea se verifica antes de comenzar la siguiente etapa.

## Preguntas abiertas

- ¿El codigo, los commits y la documentacion se escribiran en español o ingles?
- ¿Que herramienta de pruebas y que reglas de formato se adoptaran?
- ¿Que convencion se utilizara para los mensajes de commit?
