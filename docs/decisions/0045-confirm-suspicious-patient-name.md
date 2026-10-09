# ADR 0045 - Aclarar el nombre sospechoso sin corregirlo

## Estado

Aceptada.

## Contexto

La validacion por longitud y presencia de letras aceptaba nombres completos con
partes de prueba como `jhbashkda` y `junajusndqwd`. El agradecimiento generico no
permitia comprobar el dato guardado. Rechazar nombres desconocidos o quitar una
parte automaticamente puede alterar apellidos legitimos.

## Decision

Ampliar ADR 0032 con un validador local de calidad minima y un candidato pendiente
persistido. Las señales conservadoras de texto de prueba requieren confirmar la
escritura o enviar un nombre completo corregido. El backend cita todas las partes
recibidas y permite aceptar explicitamente un apellido inusual; no usa diccionarios,
no delega la escritura al LLM y no aplica reglas latinas a otros alfabetos.

Hasta aceptar el nombre no se reemplaza el registro del paciente ni se avanza al
motivo. La aceptacion muestra el nombre completo guardado. Los candidatos y mensajes
de aclaracion repetidos no se convierten en motivos ni crean citas. Una pausa
conserva el candidato, pero una afirmacion aislada no lo acepta mientras esta pausado.

## Consecuencias

- Un apellido real puede requerir un turno de confirmacion; no queda rechazado por
  la heuristica.
- La confirmacion valida la escritura recibida, no la identidad ni la creacion de
  una cita. El motivo sigue siendo obligatorio.
- El estado JSON agrega campos opcionales, sin servicios ni dependencias nuevas.
- Solo se normalizan espacios; el nombre completo aceptado alimenta el campo
  `Nombre` de la notificacion al doctor.
