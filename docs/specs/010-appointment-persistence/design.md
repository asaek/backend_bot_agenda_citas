# Diseno - Persistencia de citas

## Flujo

```text
ToolExecutor
    |
    v
PersistentCalendarProvider
    +-- ID interno -> AppointmentRepository -> SQLite
    +-- ID Google   -> GoogleCalendarProvider -> Google Calendar
```

`PersistentCalendarProvider` es un decorador de `CalendarProvider`. El adaptador
externo puede seguir usando el ID del evento para hablar con Google, pero el contrato
que recibe `ToolExecutor` expone el entero interno convertido a texto.

## Repositorio

`AppointmentRepository.upsert_synced()` busca por `(calendar_id, google_event_id)`.
Si no existe, SQLite genera el ID interno. Si existe, actualiza estado, fechas,
motivo, `last_synced_at` y `updated_at` sin cambiar `id` ni `created_at`.

El repositorio acepta una conexion SQLite abierta por la transaccion del decorador,
igual que los repositorios existentes. La restriccion de paciente se valida antes de
llamar al proveedor externo para reprogramar o cancelar.

## Seguridad y autoridad

`PatientScope` llega desde el backend. El decorador compara su `patient_id` con el
registro local antes de traducir un ID interno a un ID Google. La lista se delega al
proveedor configurado, que ya filtra los eventos Google por las propiedades privadas
del paciente.

Google Calendar conserva la autoridad sobre disponibilidad, estado, fechas y motivo.
La fila SQLite es un indice local de identidad y sincronizacion, no una segunda
fuente de verdad.

## Inicializacion

Cuando `CALENDAR_PROVIDER=google`, `main.py` construye `SQLiteDatabase` con
`DATABASE_PATH`, crea `GoogleCalendarProvider` y lo envuelve en
`PersistentCalendarProvider`. El fake por defecto permanece en memoria para pruebas
que no requieren persistencia externa.
