# Verificacion manual de `check_availability`

## Fecha

21 de septiembre de 2026.

## Alcance

Verificar desde WhatsApp el flujo conversacional de consulta de disponibilidad.
El modelo usado en esta prueba es temporal y no representa una decision de
modelo oficial para produccion.

## Entorno de prueba

- `LLM_MODEL`: `openai/gpt-oss-20b`.
- Canal: WhatsApp.
- Modelo: uso exclusivo para pruebas.
- No se registran aqui credenciales, tokens ni numeros de telefono.

## Escenario observado

1. El paciente solicito una cita para `ma;ana a las 12 pm`.
2. El chatbot pidio la fecha exacta porque no pudo resolver de forma confiable
   el texto con el error tipografico.
3. El paciente repitio la solicitud como `mañana a las 12 pm`.
4. El chatbot resolvio `mañana` como el 22 de septiembre de 2026 y consulto la
   disponibilidad de las 12:00.
5. El chatbot informo que las 12:00 estaban ocupadas.
6. El paciente solicito las 10:00 y el chatbot informo disponibilidad de 10:00
   a 10:30.

## Resultado

- [x] Se resolvio una fecha relativa cuando el texto estaba escrito
      correctamente.
- [x] Se consulto la disponibilidad del horario solicitado.
- [x] Se ofrecio un espacio alternativo de 30 minutos.
- [x] No se creo una cita: la respuesta final solo ofrecio el espacio y pidio
      confirmacion.

## Limites de esta verificacion

Esta prueba confirma el flujo observado para una conversacion real, pero no
demuestra que el modelo corrija errores tipograficos en general. La tolerancia a
errores, la fecha actual y la zona horaria deben seguir siendo validadas por el
backend antes de usar el sistema con pacientes reales.
