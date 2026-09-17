# Especificaciones

Cada funcionalidad vive en una carpeta numerada:

```text
NNN-nombre-de-la-funcionalidad/
├── spec.md
├── design.md
└── tasks.md
```

## Contenido

- `spec.md`: comportamiento observable, alcance y criterios de aceptacion.
- `design.md`: componentes, flujos, interfaces y decisiones tecnicas.
- `tasks.md`: lista ordenada de trabajo y verificaciones.

## Reglas

1. La especificacion describe el resultado, no la implementacion.
2. El diseno debe satisfacer todos los requisitos de la especificacion.
3. Las tareas deben ser pequeñas y verificables.
4. Un cambio de alcance debe reflejarse primero en la especificacion.
5. Una funcionalidad solo se considera terminada cuando cumple sus criterios de
   aceptacion.

## Especificaciones actuales

- [001 - Webhook de WhatsApp](./001-whatsapp-webhook/spec.md)

