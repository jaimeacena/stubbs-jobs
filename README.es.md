<p align="center"><img src="https://raw.githubusercontent.com/jaimeacena/stubbs-jobs/main/app/assets/stubbs.png" width="112" alt="Stubbs, el gato naranja con corbata"></p>

# Stubbs Jobs

[English](README.md)

**Tu búsqueda de empleo, organizada y bajo tu control.**

Stubbs Jobs es una app para Windows que reúne tu perfil, ofertas, currículums y candidaturas. Trabaja con un agente de IA desde su chat: el agente busca y prepara; tú decides a qué ofertas presentarte y cómo autorizar cada solicitud.

**Versión 1.0.1 · Windows de 64 bits · En español**

## Descargar y empezar

1. [Descarga Stubbs Jobs para Windows](https://github.com/jaimeacena/stubbs-jobs/releases/download/v1.0.1/Stubbs-Jobs-1.0.1-Windows-x64.zip).
2. Haz clic derecho en el ZIP → **Propiedades** → marca **Desbloquear** si aparece. Extrae **todo el ZIP** en una carpeta local que no sincronicen OneDrive, Dropbox ni Google Drive (por ejemplo `C:\StubbsJobs`) y abre **Abrir Stubbs Jobs.exe**. Python y las bibliotecas necesarias ya están incluidos.
   El acceso todavía no tiene firma digital. Si Windows muestra «Windows protegió su PC», elige **Más información → Ejecutar de todas formas**. Antes puedes comparar el ZIP con `SHA256SUMS.txt` de la misma publicación.
3. Abre un agente de IA que pueda trabajar con archivos de tu ordenador (consulta [Qué necesitas](#qué-necesitas)). Añade esa carpeta como proyecto, pega en un chat nuevo el mensaje que muestra la app y responde a sus preguntas. Puedes adjuntar tu CV o empezar sin él.
4. Cuando quieras empezar, pide **«Busca ofertas nuevas»** en ese chat.

## Qué necesitas

- Windows 10 u 11 de 64 bits.
- Un agente de IA que pueda leer y escribir archivos y ejecutar comandos en una carpeta de tu ordenador. Los chats web, como chatgpt.com o claude.ai, no pueden hacerlo. Por ejemplo:
  - **Claude Code**, en la pestaña Code de la [app de escritorio de Claude](https://claude.com/download). Necesita un plan de pago de Claude.
  - **Codex** de OpenAI ([chatgpt.com/codex](https://chatgpt.com/codex)). Necesita un plan de ChatGPT que incluya Codex.
- Para buscar y solicitar, el agente necesita además acceso a un navegador. Si un portal exige cuenta, te pedirá que inicies sesión tú; nunca te pedirá contraseñas.

La descarga no incluye cuentas, suscripciones ni acceso a portales; los costes y condiciones dependen del servicio que elijas. Cada chat nuevo lee primero las instrucciones de Stubbs Jobs, lo que consume parte de tu plan. La app abre Edge cuando está disponible o tu navegador habitual.

## Qué puedes hacer

- **Mi perfil:** guarda tu experiencia, condiciones de búsqueda y currículums. Puedes mantener varios perfiles de búsqueda.
- **Ofertas:** compara puestos, filtra resultados y consulta cada candidatura. Elige **Solicitar con revisión** para aprobar el paquete final o **Auto-solicitud** para permitir el envío de esa oferta tras las comprobaciones del agente.
- **Resumen:** consulta estadísticas históricas y resultados agrupados por día. Abre cada bloque para ver sus puestos y solicitudes; la ayuda necesaria sigue visible.

Guardar cambios o preparar el perfil no inicia una búsqueda ni un envío. Para atender lo pendiente, continúa en el chat del agente con **«Continúa con Stubbs Jobs»**.

## Portales de empleo y sus condiciones

El agente busca y solicita con tu navegador y tus cuentas. Muchos portales, como LinkedIn, Indeed o InfoJobs, prohíben en sus condiciones el uso automatizado: buscar o solicitar de forma automática puede hacer que limiten o cierren tu cuenta. Si no quieres asumir ese riesgo, usa **Solicitar con revisión** y envía tú la solicitud final, consulta las condiciones de cada portal y no pidas al agente más actividad de la que harías tú. El uso de tus cuentas es responsabilidad tuya.

## Tus datos

La descarga empieza vacía. Tu información se guarda en tu carpeta; el agente elegido puede leerla y tratarla según las condiciones de su servicio. Usa **Copias de seguridad** para conservarla. Para compartir la app, comparte el ZIP original.

Consulta el [manual de uso](docs/user-guide.md), las [novedades](CHANGELOG.md), la [recuperación de datos](docs/backup-and-recovery.md) y el [alcance y las comprobaciones pendientes](docs/limits.md).

## Código y licencia

Las instrucciones para desarrollar, comprobar y construir la app están en la [guía de desarrollo](docs/development.es.md), también disponible [en inglés](docs/development.md). El [índice de documentación](docs/README.md) dirige a los manuales, diseño y contratos. Para aportar, consulta [cómo contribuir](https://github.com/jaimeacena/stubbs-jobs/blob/main/CONTRIBUTING.md) y la [política de seguridad](https://github.com/jaimeacena/stubbs-jobs/blob/main/SECURITY.md). Los paquetes de código público contienen código genérico y pruebas ficticias; conserva los datos de una instalación personal por separado.

Creado por [jaimeacena](https://github.com/jaimeacena). La implementación, las comprobaciones y el logo han contado con apoyo de IA; consulta la [autoría](docs/authorship.md). Licencia [MIT](LICENSE); componentes y créditos en los [avisos de terceros](docs/third-party-notices.md).
