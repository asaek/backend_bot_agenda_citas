# 0002 - SQLite para la persistencia del MVP

## Estado

Aceptada y verificada en la Raspberry Pi como parte de la etapa 3. La respuesta
real de WhatsApp fue comprobada despues de renovar el token de Cloud API.

## Contexto

La etapa 3 necesita conservar pacientes de prueba, conversaciones y mensajes
entre solicitudes y reinicios. El proyecto se ejecuta inicialmente en una
Raspberry Pi y todavia no requiere concurrencia alta, consultas analiticas ni
una base compartida entre multiples instancias.

## Decision

Usar SQLite mediante `sqlite3` de la libreria estandar, con la ruta configurable
por `DATABASE_PATH` y un valor predeterminado en `data/chatbot.sqlite3`.

La logica conversacional usara repositorios como frontera de persistencia. No se
permitiran consultas SQLite directamente desde el webhook o desde la logica de
respuesta.

## Motivos

- No agrega una dependencia de infraestructura para el MVP.
- Esta disponible en Python y es adecuada para el volumen de las pruebas.
- Conserva los datos cuando el proceso se reinicia.
- Funciona localmente y en la Raspberry Pi.
- Permite probar idempotencia y continuidad con una base real.
- La frontera de repositorios permite migrar a PostgreSQL cuando exista una
  necesidad concreta.

## Consecuencias

- La base debe estar en una ruta persistente y excluida de Git.
- SQLite no sera la decision adecuada para multiples replicas o alta
  concurrencia.
- La migracion futura requerira adaptar los repositorios y el esquema.
- La etapa actual no incorpora PostgreSQL, pgvector, Redis ni colas.

## Reemplazo futuro

Si el despliegue requiere multiples procesos, alta concurrencia, respaldos
centralizados o consultas compartidas, se debe crear una nueva decision que
reemplace esta y documente la migracion a PostgreSQL.
