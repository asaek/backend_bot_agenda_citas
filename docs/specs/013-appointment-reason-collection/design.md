# Diseno - Motivo antes de crear una cita

## Estado

Implementado. La recoleccion ocurre en `ConversationService` antes de entregar la
creacion al `ToolExecutor`.

## Flujo implementado

```text
Mensaje del paciente con horario
    |
    v
LLM solicita create_appointment
    |
    v
ConversationService intercepta la mutacion
    |
    +-- guarda el horario en conversations.context_json
    +-- pregunta el nombre en cada cita y valida todas sus partes
    +-- sospecha --> conserva el nombre completo y pide confirmar/corregir
    +-- nombre aceptado --> actualiza patients.name y muestra el nombre guardado
    +-- pregunta el motivo, sin tocar el calendario
    |
    v
Siguiente mensaje del paciente
    |
    v
Validador local de calidad minima
    |
    +-- texto ilegible o ambiguo --> conserva la solicitud y pide aclaracion
    |
    +-- texto aceptable --> evaluacion estructurada
                              |
                               +-- motivo general comprensible --> politica minima acepta
                               |
                               +-- fallo tecnico/baja confianza sin respaldo --> respuesta diferenciada
                               |
                               +-- motivo insuficiente --> aclaracion progresiva
                              |
                              +-- valid --> registra metadata y reconstruye create_appointment
    |
    v
ToolExecutor -> CalendarProvider
    |
    v
Respuesta al paciente y notificacion posterior al doctor
```

## Frontera de recoleccion

`AgentOrchestrator` ya permite ejecutar un manejador antes de cualquier mutacion.
`ConversationService` usa esa frontera para interceptar `create_appointment`, aunque
el LLM haya enviado un valor para `reason`. Ese valor se descarta porque no es una
prueba de que el paciente lo haya expresado.

`PendingAppointmentReason` conserva el `start_at`, el ID de la llamada, los mensajes
entrantes que iniciaron la solicitud y entregaron el nombre, si la solicitud requiere
capturar el nombre, y los tiempos de creacion y expiracion. El indicador permite que
las solicitudes pendientes creadas antes de esta regla mantengan su comportamiento
anterior. Vincular el estado a esos mensajes evita crear la cita con el mismo texto si
WhatsApp reintenta la entrega de una pregunta. El estado se guarda bajo
`pending_appointment_reason` dentro de `conversations.context_json`, junto con
cualquier otro contexto existente. Tambien conserva `attempt_count` y
`last_evaluation` mientras espera una respuesta.
Tambien conserva el candidato completo `name_candidate` y el ultimo mensaje de
aclaracion `name_clarification_message_id`. Los campos son opcionales para mantener
compatibilidad con estados existentes y no requieren una migracion de SQLite.

## Resolucion

Antes de tomar el siguiente mensaje como nombre o motivo, `ConversationService` consulta
el router de `specs/016-conversation-intent-routing/`. Una peticion nueva explicita
limpia la solicitud de creacion pendiente y se atiende sin ejecutar `create_appointment`;
una pregunta ambigua se aclara en vez de convertirla en nombre o motivo.

En cada cita nueva, aunque el paciente ya tenga un nombre registrado,
`ConversationService` toma el siguiente mensaje, normaliza espacios, lo valida como
nombre y lo guarda o actualiza en `patients.name` junto con el marcador del mensaje
que lo entrego. La respuesta muestra el nombre completo guardado. El reintento de ese
mensaje solo devuelve esa respuesta con la pregunta por el motivo.

`patient_name_validation.py` rechaza entradas sin contenido alfabetico, fuera de
2-120 caracteres, con numeros o caracteres ajenos a un nombre, o respuestas breves
que no entregan un nombre. Permite letras Unicode, marcas combinadas, espacios,
apostrofos, guiones y puntos. Las señales de sospecha se evaluan por palabra latina:
secuencias completas de teclado, cuatro letras identicas seguidas o palabras de al
menos ocho letras con como maximo 25% de vocales y una racha de cuatro consonantes.
La `y` cuenta como vocal. No se usa esta heuristica para alfabetos no latinos.

Antes de aceptar el texto, patrones de frases completas reconocen recordatorios
de un dato ya enviado, negativas a proporcionar el nombre y expresiones de sintomas.
Para comparar se ignoran acentos, mayusculas y puntuacion; el texto normalizado
que se guarda sigue ajustando solamente espacios. Estos patrones no se aplican
a palabras sueltas de nombres o apellidos. Un resultado `invalid` mantiene el
paso de captura, el nombre previo y el candidato existente, sin efectos de agenda.
La transaccion de aceptacion guarda `name_required=false` junto con `patients.name`;
el motivo posterior no depende del historial ni de un agradecimiento textual del LLM.

Una sospecha conserva el texto completo como candidato, sin modificar `patients.name`
ni `name_required=true`. La aclaracion cita el candidato e indica como confirmarlo o
escribir un nombre completo corregido. Una afirmacion completa como `Si, es correcto`
acepta el candidato sin cambiar su escritura; una negativa lo retira como candidato
confirmable y pide el nombre completo. Las respuestas invalidas no sustituyen un
candidato pendiente; cada nombre nuevo se valida por separado. El ID de la ultima
aclaracion impide que una entrega repetida anterior cambie el nombre o cree una cita.
La pregunta al retomar una reserva pausada cita de nuevo el candidato; no se acepta
un `Si` durante la pausa. La sospecha no equivale a verificar ni rechazar una identidad.

Despues, `ConversationService` toma el siguiente mensaje como motivo, lo pasa por
`appointment_reason_validation.py` y normaliza espacios sin reemplazar el contenido
del paciente. Si el texto es evidentemente ilegible, devuelve una solicitud de
aclaracion y conserva el estado pendiente, por lo que no toca el calendario ni emite
una notificacion.

Para texto legible, `StructuredAppointmentReasonEvaluator` solicita un unico objeto
JSON al proveedor LLM. El backend valida enums, confianza y señales permitidas; una
respuesta invalida se registra con `source=error`. El LLM solo clasifica y nunca
proporciona el `reason`. Las señales detectadas localmente se combinan con las
señales permitidas del LLM, sin aceptar diagnosticos ni texto libre. Los codigos se
convierten mediante un catalogo compartido en mensajes operativos, por ejemplo
`El paciente refiere dolor ocular que podria requerir atencion prioritaria.`

El codigo `eye_redness` se detecta localmente a partir de expresiones como `ojos rojos`,
y `ocular_discharge` a partir de secrecion amarillenta, verdosa o abundante, incluso
`laga;as`. El prompt obtiene tambien `priority_signal_evidence` con objetos
`{signal, quote}`. El backend conserva interpretaciones semanticas con evidencia literal
del motivo sin exigir ademas una coincidencia con las reglas; las respuestas antiguas
sin evidencia mantienen solamente las señales locales. Las negaciones explicitas se
excluyen del respaldo local. El compositor incorpora tambien mensajes del paciente de
la gestion actual, separados de citas anteriores, y descarta texto libre del modelo,
incluidos estados como `cita confirmada`. La evidencia no se muestra al doctor.

`apply_minimum_reason_policy()` aplica la politica de ADR 0048 despues de evaluar.
Una expresion completa reconocible de molestias/problemas oculares o revision general
es un respaldo positivo, no una coincidencia de palabras sueltas. Cuando necesita
ese respaldo, registra una evaluacion `rules` con confianza `1.0` propia de la regla,
conserva las señales soportadas y no modifica el motivo. Tambien acepta una categoria
oftalmologica del LLM con confianza suficiente aunque este pida mas detalle.
El prompt distingue falta de detalle clinico de un motivo realmente ausente.

Cada intento actualiza el estado pendiente antes de responder. Un resultado
rechazado lo conserva: errores del evaluador informan del fallo tecnico y permiten
reenviar el texto; baja confianza expresa incertidumbre sin afirmar que el motivo
es ajeno o incomprensible. Las aclaraciones de contenido citan el texto legible o
reconocen una referencia anterior y usan `attempt_count`: pregunta abierta,
opciones concretas desde el segundo intento y ejemplos suficientes desde el tercero.
No hay campos persistidos nuevos ni migracion SQLite; la progresion sobrevive un reinicio.
Una evaluacion aceptada registra `last_appointment_reason_evaluation`, limpia el estado
pendiente y ejecuta la llamada reconstruida con el texto normalizado del paciente.
La politica del MVP permite continuar aun con señales de prioridad, que quedan
registradas y pueden incluirse en la notificacion interna posterior. La ejecucion usa el `PatientScope`
resuelto por el backend. Si el proveedor devuelve un error, se devuelve el error
publico y no se emite un evento de cita.

El validador aplica solamente reglas de calidad minima: no usa una lista cerrada de
sintomas y no exige un diagnostico. La evaluacion usa categorias operativas, no
clasificacion clinica. Las señales de prioridad son indicadores internos, se
describen sin nombres de enfermedades y no representan diagnosticos ni instrucciones
de atencion. Antes de usar el sistema con pacientes reales, una politica clinica
debe definir como se revisan y atienden.

La respuesta de exito se construye con la cita creada y muestra fecha, hora y motivo.
No se muestra el ID interno. La respuesta se persiste antes de intentar la
notificacion al doctor, igual que en los demas eventos de agenda.

## Integracion con notificaciones

La pregunta inicial no ejecuta `ToolExecutor`, por lo que no genera
`AppointmentNotificationEvent`. El evento se emite unicamente desde la ejecucion
exitosa posterior al mensaje que contiene el motivo.
