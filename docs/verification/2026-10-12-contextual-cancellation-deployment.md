# Despliegue - Confirmacion contextual de cancelacion

## Fecha y alcance

12/10/2026. Solicitud `local to raspberry`: sincronizacion completa del proyecto,
copia completa del `.env` local, activacion del backend y verificacion de rutas
y autenticacion de WhatsApp. Activa la correccion de ADR 0049 cuya evidencia
funcional esta en `2026-10-11-contextual-cancellation-confirmation.md`.

## Sincronizacion y configuracion

- La vista previa y la sincronizacion del proyecto confirmaron que codigo,
  pruebas y SDD ya estaban al dia en el mirror de Raspberry Pi.
- Se conservaron `.git`, `.venv`, caches, datos y archivos exclusivos del mirror;
  no se uso `--delete`.
- Se reemplazo `.env` con el archivo local completo mediante SSH/rsync.
- Comparacion byte por byte en memoria: coincide. Permisos del archivo: `600`.
- Las variables del proceso nuevo coinciden con la configuracion copiada,
  incluyendo credenciales; no se imprimieron valores ni hashes.

## Activacion del runtime

La primera conexion SSH agoto su tiempo de espera; una comprobacion posterior
confirmo conectividad y permitio continuar sin cambios durante el fallo inicial.

No se encontraron unidades systemd de proyecto, Uvicorn escuchando en el puerto
8000 ni procesos ngrok. Por tanto no habia un PID antiguo que terminar.

- Backend: detenido -> PID `5082`.
- Directorio verificado: `/home/asaek/Downloads/chatbot_test_repo`.
- Comando: `.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --no-access-log`.
- El PID nuevo es propietario del puerto y carga las variables frescas de `.env`,
  sin heredar exports de configuracion del proyecto.
- ngrok: detenido -> PID `5146`, usando el binario y la configuracion existentes.
- Tunel: `https://unthread-foam-outlast.ngrok-free.dev`, hacia el puerto 8000 y
  con `--inspect=false`.

No se modificaron citas reales ni se enviaron mensajes de prueba a WhatsApp.

## Comprobaciones

| Comprobacion | Resultado |
| --- | --- |
| `GET /` local | HTTP 200 y `{"status":"ok"}` |
| `GET /webhook/whatsapp` local | HTTP 200 y challenge esperado |
| `POST /webhook/whatsapp` local con `entry: []` | HTTP 200 y `{"status":"ok"}` |
| `GET /webhook/whatsapp` publico | HTTP 200 y challenge esperado |
| `POST /webhook/whatsapp` publico con `entry: []` | HTTP 200 y `{"status":"ok"}` |
| Configuracion efectiva de Uvicorn | Coincide con `.env` |
| Recurso de telefono de Meta, Graph API v23.0, `fields=id` | HTTP 200; sin codigos de error |

Suite ejecutada en Raspberry Pi despues de sincronizar:

```text
.venv/bin/python -m unittest discover -s tests
Ran 370 tests in 23.296s
OK
```

Los controles del webhook usan eventos vacios y la autenticacion usa una consulta
de solo lectura. No constituyen una prueba manual de cancelacion en Google real;
la cobertura funcional usa agenda, WhatsApp y LLM simulados.
