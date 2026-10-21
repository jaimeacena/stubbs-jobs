# Alcance de Stubbs Jobs 1.0

Versión 1.0.1 · 2026-10-21. Distribución portable para Windows de 64 bits.

## Comprobación por versión

El cierre comprueba código, datos ficticios y artefactos de esta versión. Sus resultados se registran en la evidencia de entrega; esta lista describe los controles y no certifica por sí sola que hayan concluido. Las comprobaciones anteriores conservan su fecha y no sustituyen las de esta versión.

- Pruebas automáticas de guardado, revisiones, concurrencia, recuperación, permisos por versión y compatibilidad de datos existentes.
- Recorridos de navegador con datos ficticios, temas claro/oscuro y anchuras de escritorio y ventanas estrechas.
- Preparación simulada: importación de CV, borrador, cambio de chat, bloqueo y recuperación, confirmación y reapertura del perfil.
- Distribución vacía extraída y ejecutada con su propio Python portable en otra carpeta del mismo equipo. Huellas de sus archivos y ausencia de datos personales verificadas.
- Reconstrucción y reapertura de una vista Excel ficticia, con fórmulas y vistas comprobadas.

## Pendiente de aceptación

- Entrevista completa desde un chat real de Codex y Claude Code con una persona. El 14/10/2026 Claude Code completó el protocolo de preparación en una descarga vacía con una persona ficticia (enfermería en México, pesos, presencial, sin CV); no sustituye una entrevista humana.
- Descarga, apertura y uso en otro ordenador Windows.
- Comprensión por una persona que no haya participado en el desarrollo y uso cotidiano.
- Accesibilidad con lector de pantalla y otras tecnologías de asistencia.
- Demostración pública completa con datos ficticios de esta misma versión.

Estas pruebas no acreditan búsquedas o solicitudes reales, resultados laborales ni ejecución desatendida. No se incluyen datos de prueba como perfil de una persona.

## Límites de funcionamiento

- Requiere un agente externo con las herramientas y permisos adecuados. La app guarda y muestra información; no inicia el chat.
- No ofrece cuentas de IA, créditos ni sesiones de portales. Un acceso comprobado puede caducar.
- Los portales de empleo pueden prohibir el uso automatizado en sus condiciones y limitar o cerrar cuentas; Auto-solicitud y las búsquedas del agente usan las cuentas de la persona bajo su responsabilidad. Solicitar con revisión permite enviar la solicitud final personalmente.
- No hay servicio en la nube, sincronización entre equipos ni actualizaciones automáticas. Crea una copia comprobada desde Copias de seguridad; docs/backup-and-recovery.md explica la actualización manual y la comparación de cambios.
- El ejecutable de apertura no tiene firma digital: Windows puede mostrar «Windows protegió su PC» la primera vez. Su apertura en un ordenador distinto no está acreditada.
- La interfaz está en español. El salario se guarda bruto anual; el agente ayuda a calcular el equivalente de un salario mensual, semanal o por horas.
- El captador automático solo lee webs con formato compatible (Greenhouse, Ashby, Lever, Workable, Personio, SmartRecruiters, Recruitee y listados HTML simples) y reconoce variantes de género, plurales y equivalentes en inglés de profesiones comunes; el resto de la búsqueda la hace el agente con su navegador.
- Las carpetas sincronizadas (OneDrive, Dropbox, Google Drive) pueden crear copias en conflicto del registro; la app avisa al detectarlas.
- Mac y Linux no forman parte de esta distribución. Una vista estrecha en el navegador no acredita compatibilidad con un teléfono físico.
- Las exportaciones son opcionales y se generan por petición; el ZIP incluye CSV, pero no las herramientas opcionales de XLSX.

Las ofertas y sus condiciones dependen de fuentes externas. Los envíos requieren el permiso correspondiente, comprobación de material y prueba del resultado; no se garantizan entrevistas ni contratación.

Beta 3 incorpora consulta pura y contexto breve, ámbitos de ejecución originales, continuación causal limitada, fundamentos históricos accesibles y cobertura del captador/navegador. since devuelve vista actual o unchanged; no calcula diferencias. Los requisitos relevantes invalidan material, mientras las webs de captación quedan separadas. Un paquete antiguo conserva identidad aunque necesite nueva revisión. Portable/fuente deben compartir procedencia de todos sus insumos.

La prueba declarada por el agente sigue requiriendo comprobación real: guardar proof no acredita la verdad de una oferta, revisión, detención o envío. Sigue pendiente un grafo uniforme de dependencias, normalizar todos los intentos, detener efectos externos de forma coordinada y medir ahorro representativo. La medición sintética de preparación del HTML no acredita rendimiento completo del navegador, ahorro de recursos real ni una validación integral de accesibilidad.
