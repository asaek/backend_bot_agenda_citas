# 0058 - Google Calendar opcional para el laboratorio Realtime

## Estado

Aceptada el 20 de octubre de 2026.

## Contexto

La voz Realtime y su cliente HTML usaban exclusivamente una agenda falsa. Una
confirmacion exitosa en ese laboratorio no creaba un evento en Google Calendar,
aunque el agente pudiera decir que la cita estaba agendada. Se solicito conservar
la pagina HTML y permitir que sus pruebas escriban en el calendario operativo
configurado.

El perfil del laboratorio sigue siendo ficticio y no tiene el `PatientScope` de
WhatsApp. Como ambos adaptadores pueden apuntar al mismo calendario, sus eventos
deben distinguirse para que el backend de pacientes no pueda listarlos ni
modificarlos como citas operativas.

## Decision

- `VOICE_CALENDAR_PROVIDER=fake` conserva el comportamiento falso por defecto y
  mantiene los tests automatizados sin escrituras externas.
- `VOICE_CALENDAR_PROVIDER=google` compone el `GoogleCalendarProvider` con las
  credenciales, calendarios y zona horaria ya configurados. La pagina HTML y la
  ruta de texto Realtime usan el mismo proveedor.
- Los eventos de voz se guardan con `managed_by=whatsapp_voice_lab`, distinto de
  `managed_by=whatsapp_chatbot`. La configuracion del laboratorio no cambia el
  proveedor ni el alcance de identidad del webhook operativo.
- El cliente HTML y `/lab/health` muestran el proveedor activo. La agenda falsa
  persiste sus snapshots en SQLite; con Google, Google Calendar es la fuente de
  verdad y el laboratorio no exige el atributo en memoria `.appointments` del fake.
- Las citas falsas preexistentes no se migran a Google automaticamente. El
  laboratorio no comparte identidad, citas ni autorizaciones con pacientes reales.

## Consecuencias

- Al habilitar Google, una confirmacion del laboratorio crea un evento real en los
  calendarios configurados y una cancelacion o reprogramacion puede modificar los
  eventos del propietario `whatsapp_voice_lab`.
- Esos eventos aparecen en Google Calendar, pero el adaptador de WhatsApp los
  excluye por su propietario distinto, aun si ambos usan el mismo calendario.
- El modo fake sigue siendo el predeterminado en desarrollo y CI. Para usar el
  laboratorio conectado se requiere configurar explicitamente
  `VOICE_CALENDAR_PROVIDER=google`.
- Esta integracion no completa Calling de Meta ni C4: el perfil continua siendo de
  laboratorio y no representa una identidad verificada del paciente operativo.
