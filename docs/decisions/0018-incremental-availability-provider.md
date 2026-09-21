# ADR 0018 - Migracion incremental del proveedor de disponibilidad

## Estado

Aceptada.

## Contexto

El contrato de las cinco herramientas de agenda ya funciona con
`FakeCalendarProvider`. La conexion de todas las operaciones a Google al mismo
tiempo aumentaria el riesgo y dificultaria aislar errores de autenticacion,
disponibilidad y zona horaria.

## Decision

`ToolExecutor` recibira un proveedor especifico para `check_availability` además
del proveedor principal. `CALENDAR_PROVIDER` continuara seleccionando el proveedor
principal y mantendra `fake` como valor predeterminado. El nuevo selector
`CALENDAR_AVAILABILITY_PROVIDER` podra usar `google`, `fake` o `primary`; cuando no
se configure, disponibilidad usara el proveedor principal.

Durante la primera fase se usara:

```text
CALENDAR_PROVIDER=fake
CALENDAR_AVAILABILITY_PROVIDER=google
```

La disponibilidad real no creara ni modificara eventos. Las demas herramientas
continuaran ejecutandose contra el fake hasta que cada una sea validada y activada.
Los slots recibidos del proveedor se filtraran con `BusinessHours` antes de
devolverlos al agente. `BusinessHours` se configurara mediante
`BUSINESS_WORKDAYS`, `BUSINESS_HOURS_START` y `BUSINESS_HOURS_END`; mientras no se
conozca el horario definitivo, conservara los valores tecnicos predeterminados.

## Consecuencias

- La primera prueba real de Google queda limitada a una operacion de solo lectura.
- Los tests del fake y del ciclo conversacional siguen siendo deterministas.
- La configuracion permite avanzar herramienta por herramienta sin duplicar el
  contrato de calendario.
- La combinacion fake/Google es solo una estrategia de migracion controlada; no se
  considera un estado final para operar con pacientes reales.
