# 018 - Reintentos de webhook sin reabrir gestiones antiguas

## Estado

Implementado y verificado con 308 pruebas en la Raspberry Pi el 8 de octubre de
2026. Backend desplegado con health, webhooks local/publico y autenticacion de
WhatsApp verificados. El bloqueo inicial por token vencido se cerro al copiar la
configuracion local actualizada, segun
`../../verification/2026-10-08-local-to-raspberry-retry-auth-recovery.md`.

## Problema

Una respuesta fallida puede reintentarse cuando el paciente ya completo otros
turnos. Regenerarla con el historial actual puede volver a pedir nombre, reabrir
una gestion terminada o repetir herramientas de agenda. El incidente del 8 de
octubre reabrio a las 11:05 una solicitud vinculada a un saludo de las 9:31,
despues de confirmar la cita a las 11:02.

## Requisitos

1. Un mensaje repetido cuya respuesta ya fue enviada devuelve HTTP 200 sin otro envio.
2. Un mensaje antiguo con turnos posteriores ya procesados devuelve HTTP 200 sin
   generar, enviar ni modificar el estado conversacional o la agenda.
3. Un reintento vigente reutiliza el texto preparado y sus eventos de cita,
   incluso despues de recrear el servicio o reiniciar el backend. No vuelve a
   consultar el modelo ni a ejecutar herramientas.
4. Solicitudes simultaneas del mismo paciente se serializan en el runtime
   Uvicorn de un proceso del MVP. Pacientes distintos pueden avanzar en paralelo.
5. La respuesta preparada se conserva antes de iniciar el envio. Cada intento
   registra su inicio, final, resultado y, cuando exista, ID del proveedor.
6. Un envio o procesamiento interrumpido con resultado incierto no se repite
   automaticamente. Se registra la condicion sin exponer textos ni credenciales.
7. El contexto del modelo termina en el mensaje que se esta procesando y excluye
   mensajes y respuestas de turnos posteriores.
8. Bases existentes y respuestas historicas fallidas siguen siendo utilizables.
   No se inventan fechas de envio ni eventos historicos que no se registraron.

## Verificacion

Pruebas integradas sin APIs: fallo antiguo seguido de cita confirmada y reintento;
reenvio del ultimo texto guardado; duplicados simultaneos; turnos distintos del
mismo paciente; independencia entre pacientes; recuperacion de respuesta preparada;
envio incierto; eventos al doctor sin repetir la mutacion. Ejecutar en la Raspberry
despues de sincronizar desde el checkout local.

## Alcance

Se mantiene SQLite y el backend de un proceso. No se agrega una cola distribuida
ni se garantiza entrega exactamente una vez ante resultados externos inciertos.
