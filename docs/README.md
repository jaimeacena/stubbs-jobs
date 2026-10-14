# Documentación de Stubbs Jobs

[Presentación en inglés](../README.md) · [Presentación en español](../README.es.md)

Los nombres de los archivos están en inglés. Los manuales y contratos operativos permanecen en español; la guía de desarrollo está disponible en ambos idiomas. Este índice orienta la lectura y no sustituye las reglas de cada operación.

| Necesito… | Consultar |
| --- | --- |
| Empezar y preparar el perfil | [Primer inicio](getting-started.md) |
| Usar la aplicación | [Manual de uso](user-guide.md) |
| Desarrollar y comprobar cambios | [Development](development.md) · [Desarrollo](development.es.md) |
| Comprender conceptos, autoridad y fuentes | [Diseño del sistema](system-design.md) |
| Dirigir o retomar una petición en el agente | [Guía del agente](agent-guide.md), desde [AGENTS.md](../AGENTS.md) |
| Consultar operaciones y sus condiciones | [Operación](operations.md) y [contrato de aplicación](application-contract.md) |
| Comprender la búsqueda autorizada | [Descubrimiento de ofertas](job-discovery.md) |
| Programar expresamente una tarea externa | [Programación opcional](scheduling.md) |
| Conservar o recuperar datos | [Copias y recuperación](backup-and-recovery.md) |
| Consultar propuestas y criterios de terminación | [Plan de trabajo](work-plan.md) |
| Conocer el alcance comprobado y los límites | [Límites de validación](limits.md) |
| Consultar cambios y componentes | [Novedades](../CHANGELOG.md), [autoría](authorship.md) y [terceros](third-party-notices.md) |

## Qué es vigente y qué es histórico

El código y sus contratos describen capacidades existentes. El plan distingue trabajo pendiente y evidencia; una propuesta no es un comando disponible. Las notas de versiones conservan sus fechas e identidad. Una comprobación automática no acredita aceptación humana, empleo real ni publicación.

El registro y los archivos vinculados conservan perfil, ofertas, tareas, permisos y pruebas. Los documentos personales son contexto opcional; no forman otra cola y no reemplazan lo confirmado en `agent-status`. Trabajar en documentación o código no autoriza búsquedas ni envíos.

## Plantillas y datos personales

La edición pública se prepara desde las plantillas genéricas de `distribution/`, mediante los constructores y sus listas explícitas. `private/` se excluye de Git. El único documento de perfil que crea el constructor es una plantilla vacía; nunca copia el contenido de la carpeta personal.
