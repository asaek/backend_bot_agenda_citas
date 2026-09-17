# Gestion de citas oftalmologicas

Este contexto describe el lenguaje del chatbot para gestionar citas con un
oftalmologo especialista en cornea.

## Lenguaje

**Paciente de prueba**:
Identidad simulada utilizada durante el MVP tecnico. Cada paciente de prueba
esta asociado a un unico numero de WhatsApp controlado por el desarrollador.
_Evitar_: Cliente, usuario, paciente real

**Cita**:
Reserva de un paciente de prueba para recibir atencion en una fecha y hora
determinadas. Durante el MVP tecnico, cada cita dura 30 minutos.
_Evitar_: Evento, reunion

**Espacio disponible**:
Periodo de la agenda del medico que puede utilizarse para crear una cita.
_Evitar_: Hueco, evento libre

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

**Señal de prioridad**:
Indicador interno derivado del mensaje que advierte que una solicitud podria
requerir atencion prioritaria. No representa un diagnostico medico.
_Evitar_: Diagnostico, estado de la cita

**Resumen conversacional**:
Sintesis interna de la conversacion que conserva la informacion relevante para
continuar la atencion, incluidas las señales de prioridad detectadas.
_Evitar_: Historial completo, nota clinica
