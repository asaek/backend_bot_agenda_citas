# Verificacion del webhook y notificaciones al doctor

## Fecha

22 de septiembre de 2026.

## Alcance

Verificar en la Raspberry Pi la integracion de las notificaciones al doctor con el
ciclo completo del webhook: cita agendada, cita modificada, cita cancelada,
aislamiento de fallos del doctor e idempotencia ante un webhook duplicado.

## Verificacion automatizada

- [x] Suite local ejecutada con dobles y proveedores fake: `151` pruebas exitosas.
- [x] Suite completa ejecutada en el mirror de Raspberry Pi con `151` pruebas
      exitosas.
- [x] Una cita agendada genero una notificacion `appointment_scheduled`.
- [x] Una cita reprogramada genero una notificacion `appointment_modified` con la
      nueva hora.
- [x] Una cita cancelada genero una notificacion `appointment_cancelled`.
- [x] Un doctor con fallo de conexion quedo en `failed` sin impedir la respuesta
      `sent` al paciente ni el envio a otro doctor.
- [x] El webhook duplicado no genero una segunda entrega al mismo doctor.

Comandos ejecutados:

```text
CALENDAR_PROVIDER=fake CALENDAR_AVAILABILITY_PROVIDER=fake uv run python -m unittest discover -s tests -v
CALENDAR_PROVIDER=fake CALENDAR_AVAILABILITY_PROVIDER=fake ~/.local/bin/uv run --directory /home/asaek/Downloads/chatbot_test_repo python -m unittest discover -s tests -v
```

Las pruebas usan dobles locales de LLM, calendario y WhatsApp; no enviaron mensajes
reales ni registran credenciales. Se observo un `StarletteDeprecationWarning` de
`TestClient`, sin impacto en el resultado.

## Verificacion operativa

El puerto `8000` ya estaba ocupado por una instancia existente del proyecto. Su
health check respondio correctamente, pero su token configurado no coincidia con el
token de prueba y la verificacion GET devolvio `403`. No se detuvo esa instancia.

Para aislar la prueba se inicio una instancia temporal del checkout sincronizado en
`127.0.0.1:18000`, con calendario fake, base SQLite temporal y
`WHATSAPP_VERIFY_TOKEN=mi-token-secreto`:

```text
GET /                         -> {"status":"ok"}
GET /webhook/whatsapp         -> 12345
POST /webhook/whatsapp        -> {"status":"ok"}
```

El POST operativo uso un evento no textual para confirmar el metodo sin invocar
proveedores externos. La instancia temporal y sus archivos fueron eliminados al
terminar la prueba.
