# 0055 - Laboratorio aislado con aiortc y Opus

## Estado

Aceptada el 18 de octubre de 2026 para el alcance A-E de laboratorio de la
[spec 021](../specs/021-whatsapp-inbound-calling/spec.md). La integracion Calling,
STT/TTS y autorizaciones de agenda de la ADR 0054 siguen propuestas.

## Decision y evidencia

Se adopta `aiortc==1.14.0` con `av==16.1.0` como extra opcional `audio`, despues
de transportar Opus en ambos sentidos en Raspberry Pi 4, Debian 13/aarch64,
CPython 3.13.5. `uv.lock` fija tambien NumPy 2.5.4 y las dependencias transitivas.
La [verificacion](../verification/2026-10-18-aiortc-audio-laboratory.md) registra
frecuencias decodificadas, reproduccion Chromium, CPU, memoria y cierre.

El laboratorio usa la factory `main:create_lab_app`, su propio proceso y SQLite
exclusivo. Desde el 20 de octubre, por solicitud del usuario tras la prueba manual,
se elimina el token Bearer de cliente/API y se conecta con un unico boton
**Conectar e iniciar llamada**. Se conserva habilitacion explicita y acceso por
loopback/SSH; la comprobacion HTTP se realiza automaticamente al conectar.
`main:app` conserva las rutas de texto; los proveedores
de agenda se componen en su lifespan para que importar la factory no abra la base
operativa. Las dependencias multimedia se importan solo al iniciar el laboratorio.
El control implementado es local al laboratorio; no se afirma completar los
eventos y el cliente Calling de C1 ni conectar Meta.

La senalizacion HTTP intercambia candidatos ICE completos sin WebSocket. La
primera conectividad probada usa candidatos host, sin STUN/TURN, entre procesos
de la misma Pi. La [verificacion LAN](../verification/2026-10-18-webrtc-client-lan.md)
comprueba tambien Chrome en macOS contra la Pi, candidatos host/UDP y saludo;
escucha humana, microfono fisico y red de Meta requieren evidencia adicional.
Un saludo WAV fijo evita acoplar la prueba de medios a servicios de voz.

Para el cliente en otra computadora se mantiene HTTP del laboratorio en loopback
y se accede por SSH desde localhost, que habilita el permiso de microfono sin
introducir certificados para la primera LAN. El transporte WebRTC sigue siendo
directo por UDP; los tuneles HTTP de SSH/ngrok no lo sustituyen. Se comprueban
HTTP sin sesion, estados ICE, RTP y reproduccion por separado. La prueba
LAN no presupone conectividad fuera de ella; STUN/TURN se decidiran con evidencia.

Las conexiones, pistas y tareas viven en memoria; SQLite conserva solo estados,
eventos y metricas. Un bloqueo exclusivo de la base impide que otro proceso
recupere como interrumpida una llamada que sigue viva. El cierre libera recursos
antes de admitir otra sesion; si falla esa limpieza, se bloquean nuevas sesiones.
Si falla SQLite, los medios se cierran igualmente y el resultado queda pendiente
de persistencia; DELETE puede reintentarlo sin volver a cerrar los medios.
`completed` describe la emision local del saludo con drenaje, no que alguien lo
haya oido; el verificador observa tambien la recepcion/reproduccion del navegador.

## Consecuencias

Se conserva el stack Python y no se introduce un servicio de medios externo. La
instalacion de audio es explicita (`uv sync --locked --extra audio`). Se acepta la
ingenieria de ICE, tareas, plazos y buffers a cambio del control directo. La
compatibilidad demostrada corresponde a las versiones y arquitectura registradas;
el extra no convierte el laboratorio en una llamada de WhatsApp.
