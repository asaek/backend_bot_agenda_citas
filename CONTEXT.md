# Gestion de citas oftalmologicas

Este contexto describe el lenguaje del chatbot para gestionar citas con un
oftalmologo especialista en cornea.

## Lenguaje

**Paciente de prueba**:
Identidad simulada utilizada durante el MVP tecnico. Cada paciente de prueba
esta asociado a un unico numero de WhatsApp controlado por el desarrollador.
_Evitar_: Cliente, usuario, paciente real

**Doctor**:
Profesional responsable de recibir la informacion operativa de las citas y el
resumen de la conversacion del paciente de prueba.
_Evitar_: Administrador, operador, paciente

**Cita**:
Reserva de un paciente de prueba para recibir atencion en una fecha y hora
determinadas. Durante el MVP tecnico, cada cita dura 30 minutos y se expresa en
una zona horaria explicita.
_Evitar_: Evento, reunion

**Espacio disponible**:
Periodo de 30 minutos de la agenda del medico que puede utilizarse para crear una
cita porque no se superpone con ningun periodo ocupado.
_Evitar_: Hueco, evento libre

**Fuente de verdad de agenda**:
Calendario o sistema autoritativo que determina la disponibilidad y el estado de
una cita. La memoria conversacional no reemplaza esta fuente.
_Evitar_: Resumen de agenda, memoria de agenda

**Horario laboral**:
Conjunto de periodos semanales en los que puede comenzar y terminar una cita,
interpretados en la zona horaria configurada para la agenda.
_Evitar_: Horario del paciente

**Periodo ocupado**:
Intervalo de una agenda que impide ofrecer un espacio disponible, sin importar el
titulo o la categoria del evento.
_Evitar_: Evento disponible

**Etiqueta interna**:
Clasificacion asociada a una cita para uso del medico y para estadisticas. Una
cita puede tener varias etiquetas y no es necesario mostrarlas al paciente.
_Evitar_: Motivo de la cita, estado de la cita, diagnostico

**Motivo de la cita**:
Descripcion proporcionada por el paciente de prueba sobre la razon de su visita.
_Evitar_: Etiqueta interna

**Estado de la cita**:
Situacion vigente de una cita dentro de su ciclo de vida.
_Evitar_: Estado del calendario

**Notificacion al doctor**:
Mensaje interno enviado al doctor despues de que una cita sea agendada,
modificada o cancelada correctamente. Incluye los datos de la cita y un resumen
de la conversacion relacionado con ese evento.
_Evitar_: Respuesta al paciente, alerta de diagnostico

**Señal de prioridad**:
Indicador interno derivado del mensaje que advierte que una solicitud podria
requerir atencion prioritaria. No representa un diagnostico medico.
_Evitar_: Diagnostico, estado de la cita

**Resumen conversacional**:
Sintesis interna de la conversacion que conserva la informacion relevante para
continuar la atencion, incluidas las señales de prioridad detectadas. Cuando se
notifica al doctor, acompaña al evento de la cita y no sustituye una nota clinica.
_Evitar_: Historial completo, nota clinica, diagnostico
