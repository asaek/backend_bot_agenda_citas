# Decisiones arquitectonicas

Esta carpeta conserva decisiones importantes cuyo contexto podria no ser
evidente al revisar solamente el codigo.

Las decisiones se numeran secuencialmente con cuatro digitos. Una decision no
se modifica para ocultar un cambio posterior; si se reemplaza, se crea otra que
indique cual decision anterior queda obsoleta.

## Indice

- [0001 - Backend con Python y FastAPI](./0001-backend-stack.md)
- [0002 - SQLite para la persistencia del MVP](./0002-sqlite-for-persistence-mvp.md)
- [0003 - Contrato de proveedor LLM](./0003-llm-provider.md)
- [0004 - Fake LLM para pruebas automatizadas](./0004-fake-llm-for-automated-tests.md)
- [0005 - Frontera del dominio de citas y herramientas](./0005-calendar-domain-boundary.md)
- [0006 - Contratos tipados para herramientas de calendario](./0006-calendar-tool-contracts.md)
- [0007 - Validacion de herramientas antes del proveedor](./0007-pre-provider-tool-validation.md)
- [0008 - Errores publicos para las herramientas de agenda](./0008-public-calendar-errors.md)
- [0009 - Proveedor falso determinista de calendario](./0009-fake-calendar-provider.md)
- [0010 - Frontera interna del ejecutor de herramientas](./0010-tool-executor-boundary.md)
