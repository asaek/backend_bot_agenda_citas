---
name: lab-tunnel
description: "Tunel de pruebas Mac-Raspberry: usar al pedir levantar el tunel SSH o abrir el laboratorio /lab. Comprueba o inicia el laboratorio, reutiliza el tunel y verifica acceso directo sin token."
metadata:
  opencode/slash: "true"
---

# Tunel de pruebas del laboratorio

Dejar accesible `/lab` desde el navegador del Mac, sin token de acceso.
El servidor y OpenAI se ejecutan desde la Raspberry.

## 1. Resolver destino y alcance

Lee `AGENTS.md`, secciones **Raspberry Pi Backend Runtime** y **Mirror Workflow**,
y `README.md`, seccion **Laboratorio de audio WebRTC**. De alli toma el usuario,
host y raiz del mirror; define `PI_SSH` y `PI_PROJECT` con esos valores actuales.
Define `LOCAL_PORT=8001`, `AUDIO_MODE=realtime` y puerto remoto `8001`. Si el usuario
pide el saludo sin API, usa `AUDIO_MODE=greeting`; respeta un puerto local solicitado.

Usa la autenticacion SSH local disponible, con `BatchMode=yes` y plazo de conexion.
Si falla, informa el bloqueo de acceso sin pedir ni guardar contraseñas en el repo.

Esta peticion usa la configuracion presente en la Pi. Si tambien se pide
`local to raspberry`, ejecuta primero esa skill, incluido su tratamiento de `.env`.
Aplica el flujo de mirror de `AGENTS.md` a cualquier cambio local que haya que ejecutar.

**Salida:** destino/raiz confirmados por SSH y modo/puerto local definidos.

## 2. Comprobar el laboratorio de la Pi

Inspecciona el listener de `127.0.0.1:8001`, sus argumentos, directorio de trabajo
y unidades systemd relacionadas (de sistema y usuario). Un laboratorio valido usa
`main:create_lab_app --factory` desde `PI_PROJECT`; conserva el PID comprobado como
`LAB_PID`. Los PID de conversaciones o documentos anteriores son solo historicos.

- **Ya activo:** comprueba `/lab/health` sin autenticacion y que
  `audio_mode` coincide con `AUDIO_MODE`. Reutiliza ese proceso si es correcto.
- **Detenido:** sigue [iniciar el laboratorio](references/start-laboratory.md).
- **Puerto ocupado por otro proceso:** informa el conflicto y detente antes de
  iniciar otro servidor o cerrar procesos ajenos.
- **Cambio de modo o reinicio solicitado:** comprueba si hay llamada/sesion de
  texto activa. Informa el bloqueo si la hay; en caso contrario reinicia solo el
  servicio/PID de laboratorio verificado, espera a que libere 8001 y arranca el
  modo pedido. Usa el arranque del enlace anterior para el proceso manual.

**Salida:** PID/servicio correcto y salud directa HTTP 200 con
`{"status":"ok","mode":"laboratory","audio_mode":"realtime"}` (o `greeting`).
Estos checks no crean una llamada ni consumen OpenAI.

## 3. Reutilizar o levantar el tunel en el Mac

Inspecciona el listener local con `lsof` y los argumentos de su proceso:

```sh
lsof -nP -iTCP:"$LOCAL_PORT" -sTCP:LISTEN
```

Reutiliza un SSH cuyo destino y forwarding correspondan a esta Pi/puerto; confirma
la ruta con el check directo del paso 4. Si pertenece a otra aplicacion o a
otro forwarding, informa el conflicto. Un puerto libre se abre con:

```sh
ssh -fN -o BatchMode=yes -o ConnectTimeout=10 \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -L "127.0.0.1:${LOCAL_PORT}:127.0.0.1:8001" "$PI_SSH"
```

Comprueba el nuevo listener y registra el PID del SSH. Si hay un tunel obsoleto
de esta tarea, verifica su PID/forwarding antes de terminar solo ese proceso y
recrearlo. Un arranque correcto de SSH por si solo no demuestra que el backend responde.

**Salida:** forwarding local en loopback hacia el laboratorio correcto.

## 4. Verificar acceso directo

Ejecuta [verificacion de acceso](references/verify-access.md): exige HTTP 200 para
salud desde Pi y Mac y para `/lab`, sin cabecera Authorization. La pagina debe
ofrecer **Conectar e iniciar llamada**, sin campo de token ni comprobacion separada.

Abrir la pagina o consultar salud no inicia OpenAI. Crear una llamada o enviar
texto si puede consumir API. Para esta preparacion basta salud/pagina; las pruebas
de conversacion requieren que el usuario las pida o pulse Conectar/Enviar.

**Salida:** URL accesible con pagina y salud comprobadas desde ambos equipos.

## 5. Informar y guiar la prueba

Entrega URL `http://localhost:<LOCAL_PORT>/lab`, modo, PID/servicio de laboratorio,
PID del tunel y resultados de acceso. Indica si se reutilizaron o iniciaron procesos.

Pide seleccionar **Micrófono**, pulsar **Conectar e iniciar llamada**, conceder permiso,
escuchar y hablar mientras responde para comprobar interrupcion. El panel muestra
limites/metricas del modo Realtime; revisa los limites configurados, sin ampliar
cuotas ni cambiar perfil/base para eludirlas.

El cliente debe abrirse en localhost o HTTPS para habilitar microfono. El tunel
lleva HTTP; WebRTC usa UDP directo entre Mac y Pi, inicialmente en la misma LAN.
Si HTTP pasa pero ICE falla, revisa VPN, aislamiento Wi-Fi y firewall UDP, y
reporta por separado el transporte. La escucha fisica necesita validacion humana.

Para cerrar el tunel cuando se solicite, termina unicamente su PID verificado.
El servidor manual y el tunel deben levantarse de nuevo tras reiniciar sus equipos.
