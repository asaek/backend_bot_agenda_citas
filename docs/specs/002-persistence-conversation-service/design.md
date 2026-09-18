# Diseño tecnico: persistencia y Conversation Service

## Estado

Verificado en la Raspberry Pi. La recepcion, persistencia y envio real fueron
comprobados despues de renovar el token de Cloud API.

## Componentes

- `main.py`: recibe el webhook, valida el JSON y coordina el servicio y el
  cliente de WhatsApp.
- `persistence.py`: abre conexiones SQLite, crea el esquema y gestiona
  transacciones.
- `repositories.py`: accede a pacientes, conversaciones y mensajes.
- `conversation_service.py`: identifica al paciente, recupera la conversacion,
  registra mensajes y decide la respuesta automatica.
- `whatsapp_client.py`: envia mensajes mediante WhatsApp Cloud API y no conoce
  la persistencia.

## Persistencia

Se usara SQLite mediante `sqlite3` de la libreria estandar. La ruta se obtiene de
`DATABASE_PATH` y tendra como valor predeterminado `data/chatbot.sqlite3`.
El directorio `data/` y los archivos de base de datos quedan excluidos de Git.

La base tendra estas tablas:

- `patients`: numero de WhatsApp, nombre opcional y fechas de actividad.
- `conversations`: paciente, estado, estado conversacional, contexto JSON y
  fechas de actividad.
- `messages`: conversacion, direccion, ID del proveedor, texto, tipo, estado,
  relacion con el mensaje respondido y fecha UTC.

La base aplicara una restriccion unica al identificador del proveedor por
direccion y un indice unico que limite a una conversacion activa por paciente.

## Flujo de un mensaje

```text
Webhook
  |
  v
Extraer mensaje de texto
  |
  v
Buscar o crear paciente por `from`
  |
  v
Buscar o crear conversacion activa
  |
  v
Guardar mensaje entrante
  |
  v
ConversationService genera respuesta fija
  |
  v
WhatsAppClient envia la respuesta
  |
  v
Guardar respuesta como `sent` o `failed`
```

El envio a WhatsApp ocurre fuera de la transaccion SQLite. Si falla, se abre una
nueva transaccion para conservar el estado `failed`. Esta etapa acepta una
semantica de entrega al menos una vez; no promete una transaccion distribuida
entre SQLite y WhatsApp Cloud API.

## Idempotencia

Antes de insertar un mensaje entrante se consulta su `provider_message_id`. Si
ya existe y tiene una respuesta `sent`, el webhook no vuelve a enviar. Si no
existe una respuesta o la respuesta esta `failed`, se permite el reintento.

El ID de la respuesta devuelto por WhatsApp se guarda cuando esta disponible.

## Estado conversacional

El estado inicial sera `new` y pasara a `active` despues del primer mensaje.
El contexto se almacenara como JSON preparado para datos del flujo de citas,
pero no se extraeran datos semanticos ni se generaran resumenes en esta etapa.

## Configuracion

| Variable | Uso |
| --- | --- |
| `DATABASE_PATH` | Ruta de la base SQLite local |
| `WHATSAPP_VERIFY_TOKEN` | Token de verificacion de Meta |
| `WHATSAPP_ACCESS_TOKEN` | Credencial de envio mediante Cloud API |
| `WHATSAPP_PHONE_NUMBER_ID` | Numero desde el que se responde |

## Evolucion

El `ConversationService` dependera de repositorios, no de consultas SQLite
directas. Esa frontera permite sustituir SQLite por PostgreSQL cuando el alcance
lo requiera sin cambiar la logica conversacional.
