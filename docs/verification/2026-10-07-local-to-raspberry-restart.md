# Verificacion de reinicio obligatorio en local to raspberry

## Fecha y estado

7 de octubre de 2026. Skill actualizada y reinicio verificado en Raspberry Pi.

## Flujo operativo

La skill `.agents/skills/local-to-raspberry/SKILL.md` define ahora el flujo completo
`sincronizar → reiniciar → verificar`. El reinicio y las comprobaciones son
obligatorios incluso si la sincronizacion no encuentra diferencias o solo copia
documentacion, salvo una solicitud explicita de sincronizar sin reiniciar.

`AGENTS.md` enlaza la skill desde Mirror Workflow para que futuras solicitudes
`local to raspberry` sigan el procedimiento completo. README explica el mismo
contrato operativo. La skill exige confirmar el reinicio con un PID nuevo o
estado del servicio y comprobar HTTP 200 y el cuerpo esperado en cada ruta.

## Sincronizacion y reinicio

- Se reviso el estado local y la vista previa de rsync. Los archivos transferidos
  antes del reinicio fueron la skill, `AGENTS.md` y `README.md`.
- Se comprobaron unidades systemd de sistema y usuario, listener, comando y directorio.
  No se encontraron unidades chatbot/uvicorn; el backend estaba gestionado manualmente.
- Se envio SIGTERM solamente al PID verificado `2368706`, se confirmo que termino y
  que el puerto quedo libre.
- Se inicio el comando estandar desde `/home/asaek/Downloads/chatbot_test_repo`.
  El nuevo PID `2434069` se confirmo como propietario de `127.0.0.1:8000` y con
  directorio de trabajo correcto.
- El tunel ngrok existente estaba activo con PID `19472`.

## Comprobaciones HTTP despues del reinicio

Se uso curl. El verify token se cargo en memoria y se paso por entrada estandar de
configuracion sin imprimirlo. Los POST contenian un evento sin mensajes para
comprobar la ruta sin ejecutar el LLM, enviar WhatsApp ni modificar citas.

| Ruta | Local | Publica (ngrok) |
| --- | --- | --- |
| `GET /` | `200 {"status":"ok"}` | — |
| `GET /webhook/whatsapp` | `200 12345` | `200 12345` |
| `POST /webhook/whatsapp` | `200 {"status":"ok"}` | `200 {"status":"ok"}` |
