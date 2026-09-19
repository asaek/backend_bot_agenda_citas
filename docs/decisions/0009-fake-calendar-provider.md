# 0009 - Proveedor falso determinista de calendario

## Estado

Aceptada para el incremento del proveedor falso del contrato de herramientas.

## Contexto

El contrato `CalendarProvider` necesita probar disponibilidad, conflictos y
transiciones de citas sin depender de red, credenciales o datos variables de
Google Calendar. Las pruebas tambien deben poder provocar errores del proveedor
de manera repetible.

## Decision

Se implementa `FakeCalendarProvider` en memoria con la misma interfaz asincrona
que `CalendarProvider`. Su estado inicial acepta calendarios, periodos ocupados y
citas. Las respuestas se ordenan de forma estable, las citas nuevas reciben IDs
secuenciales y la creacion elige el primer calendario disponible en el orden de
configuracion.

Los periodos ocupados y las citas `scheduled` o `confirmed` bloquean slots de 30
minutos. Crear o reprogramar un intervalo bloqueado lanza `SlotUnavailable`.
Listar filtra por paciente y rango; reprogramar conserva ID y calendario; cancelar
conserva la cita con estado `cancelled`.

El fake permite simular cualquier error publico de calendario de forma persistente
o una sola vez. El consumidor puede envolver la operacion con
`execute_with_public_errors` para verificar el resultado que recibira el agente.

## Consecuencias

- Las pruebas del contrato son locales, rapidas y deterministas.
- Los conflictos atomicos del proveedor se pueden probar antes de integrar Google.
- La implementacion futura de Google debe conservar la misma interfaz y semantica
  publica de errores.
- El fake no representa persistencia ni disponibilidad real de Google Calendar.

## Alternativas descartadas

- Mockear cada metodo por separado sin un estado de agenda compartido.
- Reutilizar SQLite como sustituto del proveedor externo.
- Hacer que las pruebas dependan de fechas o eventos reales de Google Calendar.
