# Verificacion de citas manuales de Google Calendar

## Fecha

29 de septiembre de 2026.

## Cambio

Los eventos creados por el bot siguen identificandose mediante sus propiedades
privadas. Un evento creado por el medico o su secretaria se puede listar y modificar
solo cuando su descripcion incluye una linea `WhatsApp: +<E.164>` cuyo numero
coincide exactamente con el remitente resuelto por el backend. El marcador se quita
del motivo antes de entregar la cita al agente. Eventos sin marcador o con otro
numero permanecen ocultos.

## Reproduccion y regresion

La prueba de `GoogleCalendarProvider` simula una cita manual sin propiedades privadas,
otra con un numero similar y otra sin identificador. Antes del cambio, la prueba
fallo porque solo recibio `bot-event` y omitio `manual-event`. Despues del cambio,
la cita marcada se lista y se puede cancelar, y el evento marcado con el numero de
otra persona no se puede modificar.

Comando de regresion ejecutado en la Raspberry Pi:

```text
PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -m unittest test_google_calendar_provider.GoogleCalendarProviderTests.test_list_includes_manual_events_with_exact_whatsapp_marker test_google_calendar_provider.GoogleCalendarProviderTests.test_manual_event_with_exact_whatsapp_marker_can_be_cancelled test_google_calendar_provider.GoogleCalendarProviderTests.test_manual_event_with_another_phone_is_not_modifiable test_google_calendar_provider.GoogleCalendarProviderTests.test_list_follows_pages_and_requires_private_metadata -v
```

Resultado: 4 pruebas `OK`.

La suite completa se ejecuto con:

```text
PYTHONPATH=/home/asaek/Downloads/chatbot_test_repo:/home/asaek/Downloads/chatbot_test_repo/tests /home/asaek/Downloads/chatbot_test_repo/.venv/bin/python -m unittest discover -s /home/asaek/Downloads/chatbot_test_repo/tests -q
```

Resultado: `Ran 204 tests ... OK`.

## Verificacion HTTP aislada

Con Uvicorn temporal, una base SQLite temporal, `CALENDAR_PROVIDER=fake` y un token
de verificacion de prueba:

- `GET /` -> `200 {"status":"ok"}`.
- `GET /webhook/whatsapp` -> `200 12345`.
- `POST /webhook/whatsapp` con un evento vacio -> `200 {"status":"ok"}`.

Las pruebas de agenda usan `httpx.MockTransport`; no acceden a Google Calendar real ni
envian mensajes a WhatsApp. Las citas manuales existentes deben recibir la linea
`WhatsApp: +<E.164>` una vez; las nuevas deben incluirla desde que se crean.
