# ADR 0031 - Asociacion segura de citas manuales por WhatsApp

## Estado

Aceptada, implementada y verificada con HTTP simulado en la Raspberry Pi.

## Contexto

El calendario del medico es la fuente de verdad y tanto el chatbot como el medico o
su secretaria pueden crear citas. El adaptador ya lista eventos creados por el bot,
pero Google Calendar no añade las propiedades privadas del paciente a los eventos
introducidos manualmente. Como el calendario compartido contiene citas de varias
personas, listar todos los eventos o asociarlos solo por nombre puede exponer citas
ajenas.

## Decision

Las citas creadas por el bot conservan la asociacion privada existente mediante
`managed_by=whatsapp_chatbot` y `patient_id`. Para reconocer una cita creada
manualmente, la descripcion debe contener una linea completa con este formato:

```text
WhatsApp: +<numero E.164>
```

El adaptador compara el numero de forma exacta con el remitente de WhatsApp resuelto
por el backend. No usa el nombre del paciente, coincidencias parciales ni eventos sin
marcador. El backend quita la linea del motivo que se entrega al agente. Las mismas
reglas de propiedad se aplican al listar, reprogramar o cancelar una cita.

## Consecuencias

- Google Calendar sigue siendo la fuente de verdad para las citas del medico y del bot.
- El medico o la secretaria deben incluir el marcador en cada cita manual nueva.
- Las citas manuales existentes requieren una actualizacion unica de la descripcion.
- Una cita manual sin marcador se mantiene oculta al paciente hasta que se identifique.
- Las propiedades privadas y la proteccion contra acceso a citas ajenas se conservan.
