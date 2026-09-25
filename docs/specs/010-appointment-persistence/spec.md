# 010 - Persistencia de citas

## Estado

Implementado y verificado en el mirror de Raspberry Pi. Google Calendar sigue
siendo la fuente de verdad de la agenda.

## Objetivo

Separar la identidad local de una cita de la identidad del evento externo y conservar
un registro sincronizable para que las herramientas no dependan del ID de Google.

## Modelo persistente

La tabla `appointments` usa SQLite y contiene:

- `id`: entero autoincremental, ID interno usado por las herramientas para futuras
  modificaciones; no forma parte de los detalles mostrados al paciente.
- `calendar_id`: calendario Google donde vive el evento.
- `google_event_id`: ID del evento en Google Calendar.
- `patient_id`: paciente de prueba asociado, con referencia a `patients`.
- `status`: estado normalizado de `AppointmentStatus`.
- `start_at`, `end_at`: fechas ISO 8601 con zona horaria.
- `reason`: motivo de la cita.
- `last_synced_at`: instante UTC de la ultima lectura o escritura confirmada.
- `created_at`, `updated_at`: fechas UTC del registro local.

Existe una restriccion unica sobre `(calendar_id, google_event_id)` y un indice por
`(patient_id, start_at, id)`.

## Requisitos funcionales

### RF-1001 - Identidad separada

El `id` interno debe ser diferente del `google_event_id`. El proveedor persistente
debe traducir el ID interno recibido por reprogramar/cancelar al ID externo antes de
llamar a Google.

### RF-1002 - Sincronizacion

Cada cita creada, listada, reprogramada o cancelada correctamente debe insertar o
actualizar su registro y modificar `last_synced_at`. La sincronizacion debe conservar
el mismo ID interno cuando se reencuentra el mismo evento.

### RF-1003 - Fuente de verdad

El estado, las fechas y el motivo obtenidos de Google actualizan el registro local.
SQLite no debe inventar disponibilidad ni sustituir el estado del proveedor.

### RF-1004 - Aislamiento por paciente

Una operación de modificación que use un ID interno perteneciente a otro paciente
debe devolver `AppointmentAccessDenied`. Una lista solo debe devolver citas del
`PatientScope` actual.

### RF-1005 - Historial de cancelacion

Cancelar una cita actualiza su estado a `cancelled`; no elimina el registro local.

## Criterios de aceptacion

1. La inicializacion SQLite crea `appointments` con las columnas y restricciones
   definidas.
2. El repositorio puede insertar, reencontrar y actualizar una cita sin cambiar su
   ID interno.
3. El proveedor persistente devuelve IDs internos y conserva el ID Google separado.
4. Reprogramar y cancelar traducen el ID interno al evento Google correcto; ambos
   flujos conservan el mismo ID interno despues del `PATCH`.
5. `last_synced_at` cambia despues de una sincronizacion exitosa.
6. Un paciente no puede modificar ni consultar mediante ID una cita ajena.
7. Las pruebas no necesitan una cuenta real de Google.

## Fuera del alcance

- Sincronizacion en segundo plano o reconciliacion periodica.
- Recuperacion de eventos borrados directamente desde Google.
- Migracion de citas existentes antes de esta tabla.
- Reemplazar Google Calendar como fuente de verdad.
