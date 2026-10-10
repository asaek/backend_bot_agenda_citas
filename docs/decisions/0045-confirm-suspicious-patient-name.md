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

La calidad minima distingue tambien respuestas conversacionales reconocibles de
un nombre. Se rechazan recordatorios como `ya te lo habia dich`, negativas a dar
el nombre y expresiones completas de sintomas como `Tengo los ojos rojos`, aunque
solo contengan letras. Las reglas locales normalizan acentos y mayusculas para
comparar frases, sin alterar el nombre recibido ni usar diccionarios. Un rechazo
no guarda un candidato nuevo, no reemplaza el nombre previo y no cambia de paso.
Si ya habia un candidato sospechoso, sigue pendiente hasta su confirmacion o correccion.

## Consecuencias

- Un apellido real puede requerir un turno de confirmacion; no queda rechazado por
  la heuristica.
- La confirmacion valida la escritura recibida, no la identidad ni la creacion de
  una cita. El motivo sigue siendo obligatorio.
- El estado JSON agrega campos opcionales, sin servicios ni dependencias nuevas.
- Solo se normalizan espacios; el nombre completo aceptado alimenta el campo
  `Nombre` de la notificacion al doctor.
