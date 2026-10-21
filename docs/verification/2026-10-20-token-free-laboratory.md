# Acceso al laboratorio sin token

## Resultado

20 de octubre de 2026. Se elimino el token de acceso del cliente y la API de
laboratorio por solicitud del usuario. **Conectar e iniciar llamada** comprueba
HTTP automaticamente y comienza WebRTC; **Colgar** permite cerrar y reconectar.
Texto e historial tambien funcionan sin cabecera Authorization.

El laboratorio Realtime esta disponible desde el Mac en
`http://localhost:8001/lab`, con microfono seleccionado por defecto.

## Verificacion ejecutada en la Raspberry

- Suite completa: **453 tests, OK**, incluidos medios reales RTP/Opus.
- `scripts/verify_lab_controls.py`: Chromium/WebRTC real con Realtime falso,
  conexion sin token, historial compartido, reintento sin duplicados y texto
  posterior a colgar. Sin errores JavaScript ni llamadas a APIs externas.
- `scripts/verify_lab_browser.py`: saludo reproducido, audio en ambos sentidos,
  conexion/cierre/reconexion sin token, cierre concurrente, reintento tras 503,
  perdida de medios, apagado y respuestas HTTP/microfono tardias. Sin errores
  JavaScript. Par ICE host/host UDP; saludo de 5.129 s.
- Estas comprobaciones usan bases temporales y proveedores falsos; no consumen
  OpenAI ni sustituyen la escucha o el microfono fisicos del usuario.

## Sincronizacion y runtime

Se sincronizaron exclusivamente los archivos del cambio con sus rutas relativas.
Se copio el `.env` local completo; igualdad byte a byte comprobada en memoria y
permisos remotos `600`, sin imprimir valores ni hashes.

Se verificaron procesos, directorio y listeners antes de recargar:

| Proceso | PID anterior | PID nuevo | Resultado |
| --- | --- | --- | --- |
| Backend `main:app`, 127.0.0.1:8000 | 42741 | 257324 | Salud y configuracion comprobadas |
| Laboratorio `main:create_lab_app`, 127.0.0.1:8001 | 42742 | 257384 | Realtime, sin token, configuracion comprobada |
| SSH del Mac, localhost:8001 -> Pi:8001 | 8546 | 8546 | Reutilizado, destino y forwarding comprobados |

No habia sesiones de voz/texto activas al reiniciar. Se conservaron bases,
perfil y cuota efectivos del laboratorio. El ngrok existente siguio activo.
El primer intento de recarga encontro un socket en TIME_WAIT tras terminar el
backend; se comprobo que no hubiera listener y se completo el arranque con el
PID nuevo indicado arriba.

| Comprobacion HTTP | Resultado |
| --- | --- |
| `GET /` local | 200, `{"status":"ok"}` |
| `GET /webhook/whatsapp` local y publico | 200, challenge correcto |
| `POST /webhook/whatsapp` local y publico, evento vacio | 200, `{"status":"ok"}` |
| `GET /lab/health`, Pi y Mac, sin token | 200, laboratorio Realtime |
| `GET /lab`, Pi y Mac | 200; boton directo y ausencia de campos/botones antiguos |
| Cabeceras del laboratorio | `Cache-Control: no-store` |
| GET de solo lectura del numero en Graph API v23.0 | 401, codigo 190/subcodigo 463 |

La credencial externa de envio WhatsApp sigue vencida, como en la comprobacion
anterior del hito Realtime. Es independiente del token de acceso eliminado del
laboratorio; no impide usar `/lab`.
