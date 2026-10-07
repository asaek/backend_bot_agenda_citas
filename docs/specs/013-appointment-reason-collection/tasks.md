# Tareas - Motivo antes de crear una cita

## Corte 1 - Estado pendiente

- [x] Definir el estado pendiente de una solicitud de creacion.
- [x] Persistir el horario y la expiracion en el contexto de la conversacion.
- [x] Descartar el motivo propuesto por el LLM hasta recibir el mensaje del paciente.

## Corte 2 - Ejecucion segura

- [x] Interceptar `create_appointment` antes del proveedor.
- [x] Ejecutar la cita con el texto del siguiente mensaje del paciente.
- [x] Emitir eventos y notificaciones solo despues de una creacion exitosa.

## Corte 3 - Verificacion

- [x] Probar que la primera solicitud pregunta el motivo y no crea una cita.
- [x] Probar que el motivo recibido se persiste en la cita.
- [x] Probar continuidad despues de reiniciar `ConversationService`.
- [x] Ejecutar la suite completa en el mirror de Raspberry Pi.
- [x] Verificar health check y ambos metodos del webhook en el mirror.

## Corte 4 - Calidad minima del motivo

- [x] Crear un validador independiente para normalizar y evaluar el texto.
- [x] Rechazar entradas vacias, no textuales, demasiado cortas o evidentemente
      ilegibles.
- [x] Mantener la solicitud pendiente cuando el motivo sea rechazado.
- [x] Permitir continuar con un motivo valido posterior sin repetir el horario.
- [x] Cubrir el caso `jnbajnbsdijkqnbwikbdqwd` sin crear una cita.
- [x] Ejecutar la suite completa y verificar el webhook en el mirror de Raspberry Pi.

## Corte 5 - Evaluacion estructurada y estado enriquecido

- [x] Definir enums para calidad, categoria y señales de prioridad.
- [x] Validar la respuesta JSON del LLM sin aceptar motivos generados.
- [x] Aplicar confianza minima y degradar respuestas invalidas a aclaracion.
- [x] Persistir intentos, resultado, categoria, señales y fecha de evaluacion.
- [x] Conservar el texto normalizado del paciente como unico `reason` de la cita.
- [x] Mantener las señales de prioridad como metadata sin activar triage clinico.

## Corte 6 - Señales de prioridad sin diagnostico

- [x] Definir codigos y descripciones operativas para perdida visual, dolor, trauma,
      exposicion quimica, sangrado, destellos, ojos rojos y alteraciones visuales importantes.
- [x] Filtrar señales no soportadas o diagnosticos enviados por el LLM.
- [x] Reutilizar las descripciones seguras al componer la notificacion al doctor.
- [x] Rechazar referencias vagas como `Lo de siempre` sin perder el horario pendiente.
- [x] Cubrir entradas invalidas, motivos validos, horario de la 1 pm, una señal de
      prioridad y ausencia de notificacion mientras el motivo sea invalido.
- [x] Documentar que la politica clinica para pacientes reales queda pendiente.
- [x] Detectar ojos rojos aunque el LLM omita la señal y filtrar señales libres del resumen.
- [x] Verificar `eye_redness` y su inclusion en la notificacion en Raspberry Pi.

## Corte 7 - Nombre del paciente en cada cita

- [x] Solicitar el nombre al iniciar cada cita nueva, incluso si ya esta registrado.
- [x] Guardar o actualizar el nombre en `patients.name` junto con el estado pendiente.
- [x] Evitar que un reintento del mensaje del nombre se procese como motivo.
- [x] Cubrir el flujo para un paciente con nombre previo: nombre, motivo y cita.
- [x] Ejecutar la suite completa y verificar health check y ambos metodos del webhook
      en el mirror de Raspberry Pi.

## Corte 8 - Evaluacion semantica y secrecion ocular

- [x] Añadir secrecion ocular amarillenta, verdosa o abundante y variantes de escritura.
- [x] Unificar catalogo e instrucciones semanticas con el resumidor de notificaciones.
- [x] Aceptar señales interpretadas con evidencia literal del motivo, sin exigir regex.
- [x] Mantener compatibilidad con respuestas sin evidencia mediante el respaldo local.
- [x] Excluir negaciones explicitas y no forzar prioridad ante pocas lagañas al despertar.
- [x] Ejecutar la suite completa en Raspberry Pi y registrar la verificacion en
      `docs/verification/2026-10-07-semantic-priority-signals.md`.
