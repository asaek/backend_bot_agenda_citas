# Documentacion del proyecto

Esta carpeta contiene las decisiones, especificaciones y planes que guian la
implementacion del chatbot de WhatsApp.

## Flujo SDD

Cada funcionalidad se desarrolla siguiendo este orden:

1. `spec.md`: define el problema, el alcance y los criterios de aceptacion.
2. `design.md`: describe la solucion tecnica acordada.
3. `tasks.md`: divide el trabajo en pasos verificables.
4. Implementacion.
5. Verificacion contra los criterios de aceptacion.

La implementacion no debe comenzar hasta que la especificacion y el diseno
esten aprobados.

## Estados

- **Borrador**: todavia contiene preguntas o decisiones abiertas.
- **Aprobado**: el alcance y el diseno fueron confirmados.
- **Implementado**: el codigo fue terminado.
- **Verificado**: los criterios de aceptacion fueron comprobados.

## Indice

- [Lenguaje del dominio](../CONTEXT.md)
- [Proyecto](./project.md)
- [Arquitectura](./architecture.md)
- [Convenciones](./conventions.md)
- [Especificaciones](./specs/README.md)
- [Decisiones](./decisions/README.md)
- [Verificaciones](./verification/2026-09-21-whatsapp-check-availability.md)
