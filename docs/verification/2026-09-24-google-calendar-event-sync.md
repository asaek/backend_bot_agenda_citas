# Verificacion - Sincronizacion de eventos de Google Calendar

## Diagnostico

En la Raspberry, dos citas que SQLite habia guardado como `confirmed` fueron
devueltas por Google con estado `cancelled` y con una hora de actualizacion posterior.
No habia mensajes entrantes de cancelacion ni notificaciones internas de
`appointment_cancelled`; el backend estaba leyendo el estado real de Google y,
ademas, solicitaba sus tombstones con `showDeleted=true`.

## Correccion verificada

- Las mutaciones usan `sendUpdates=all`.
- Los listados usan `showDeleted=false` y descartan defensivamente estados
  `cancelled`.
- El proveedor fake aplica la misma regla de listar solo citas vigentes.

## Comandos

En el mirror de Raspberry Pi:

```bash
uv run python -m unittest discover -s tests -v
```

Resultado: 156 pruebas correctas.

La verificacion HTTP temporal del mirror devolvio:

```text
health={"status":"ok"}
verify=12345
post={"status":"ok"}
```

La consulta de la fecha afectada ya no devuelve citas canceladas al agente. Las
citas que Google ya cancelo no se restauran automaticamente; deben agendarse de
nuevo o restaurarse manualmente en Google Calendar.
