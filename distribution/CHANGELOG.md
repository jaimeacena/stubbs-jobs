# Notas de cambios

## Stubbs Jobs 1.0 · 1.0.0 · 2026-10-09

- Primera publicación 1.0 para Windows x64, con descarga vacía y código genérico bajo la cuenta jaimeacena.
- README breve para empezar y guía de desarrollo separada; conserva los manuales, permisos por oferta y recuperación.
- Identidad estable compartida por app, código y descarga, con huellas de procedencia y componentes incluidos.
- Comprobaciones del código público en GitHub para cada cambio, con dependencias fijadas y datos ficticios.
- El mantenimiento del icono vuelve a intentarlo si Windows tarda en responder y termina al perder la ventana propia.
- Las comprobaciones de CV reconocen rutas equivalentes de Windows y mantienen el bloqueo de archivos externos; las pruebas usan rutas físicas para comprobar la misma carpeta en cualquier instalación.

## Stubbs Jobs Beta 4 · 0.1.0-beta.4 · 02/10/2026

- Stubbs naranja cálido con corbata grafito y hombros discretos en camisa clara, sobre fondo transparente. La misma imagen se usa en la interfaz y origina el icono multirresolución del ejecutable, la ventana de Windows y el favicon; este renueva su identidad cuando cambia el archivo. Sustituye la variante anterior en todos los recursos activos. Acciones terracota y superficies piedra; tema oscuro con fondos, superficies, textos y líneas grafito neutros. Tipografía, espaciado, foco y controles coherentes.
- Escritorio con tabla más amplia y compacta, encabezados y empresa visibles al desplazarse, orden directo y filtros explícitos que conservan la consulta.
- Mi perfil con tres apartados y su índice, en este orden: Sobre mi, Lo que busco y Currículums. Las tarjetas compactas de PDF están en su panel propio, cerradas por defecto, con archivo, resumen de usos y Abrir PDF visible cuando está disponible. Al desplegar muestran ofertas actuales o históricas, estado y fecha registrada. Los controles nativos funcionan de manera independiente y conservan su apertura durante la navegación y actualización de la misma página, sin guardar el perfil ni iniciar trabajo sobre ofertas; no se promete conservarla tras recargar o cerrar. Los documentos que comparten nombre siguen separados. La asociación se comprueba por el contenido del PDF y conserva el historial aunque falte el archivo. Sobre mi y Lo que busco no tienen subgrupos internos. Lo que busco incluye las solicitudes anteriores y las empresas que se deben evitar, con su funcionamiento explicado. Experiencia a todo el ancho y fuentes opcionales explicadas. Conserva los cuatro borradores existentes, el guardado único y la orientación hacia los errores sin perder ediciones. Espacios entre campos, ayudas y formularios homogéneos.
- Teclado con Ctrl+K para buscar, Ctrl+S para guardar ediciones y Escape para cerrar menús; retorno a la oferta de origen.
- Experiencia de escritorio pulida: pestañas de estado como control segmentado con su número, Añadir oferta en el encabezado, Estado con etiquetas y punto de color, filtros de columna que aparecen al usarlos y nombres publicados en mayúsculas mostrados en mayúsculas y minúsculas. La ficha separa lectura y decisión: un panel lateral fijo reúne estado, los dos modos de solicitud con el mismo tamaño y Condiciones. Autorizar envío flota centrado, Resumen se lee por días con Hoy y Ayer, los formularios muestran Ctrl S y la carga inicial enseña la silueta de Ofertas. Escape también sale de la selección múltiple.
- Una sola reconstrucción al cambiar de pestaña y preparación de valores de filtro bajo demanda.
- Respuestas opcionales editables con ámbito y significado declarados; preguntas numéricas admiten decimales válidos y se reutiliza el preaviso cuando lo pide el formulario. Salarios publicados ambiguos conservan su moneda y unidad; las fechas sin hora conservan su día.
- Decisiones de selección con identidad independiente de la fecha; cambios de tareas detectados incluso en el mismo segundo. Editar la explicación conserva la fecha del trabajo real. Una autorización manual nueva no hereda la continuación automática anterior. Los bloqueos resueltos permanecen en el historial y dejan de mostrarse como actuales. Las confirmaciones de envío comprueban el inicio autorizado y la fecha del recibo; las revisiones de fuentes conservan su precisión temporal al finalizar.
- Recuperación fuera de la instalación original, con apertura disponible solo tras completar las comprobaciones; las copias incluyen también CV antiguos visibles sin uso registrado. Excel conserva campos de distintas filas, monedas acreditadas, fuentes originales y un solo primer hito por proceso/tipo. El código público incluye pruebas de estas correcciones y el contrato vigente de interfaz.
- Revisión de producción: la interfaz se sirve con tipos de contenido fijos aunque Windows tenga otras asociaciones de archivos; cabeceras adicionales de aislamiento; nombres de empresa escapados en la edición conjunta; fallos inesperados del servicio registrados de forma acotada en data/app-server.log, sin contenido de las peticiones. El escritor rechaza tipos de dato que impedirían abrir la app (empresa, puesto, enlace, bloqueos e historial) y los informes toleran fechas incompletas. Sustitución de archivos con reintento breve en Windows, instantáneas nuevas del registro comprimidas y captación que respeta la codificación declarada por cada web. En la ficha, Condiciones reúne en una línea los datos no publicados; la tabla atenúa los datos ausentes, el título del formulario de solicitud se lee como título y el Resumen omite las direcciones técnicas de las incidencias.

Las comprobaciones de esta entrega se detallan en [LIMITES.md](LIMITES.md). Los ejemplos visuales son ficticios; no acreditan trabajo real ni aceptación humana.

## Stubbs Jobs Beta 3 · 0.1.0-beta.3 · 02/10/2026

- Consulta del agente sin escritura, contexto breve y ampliación por oferta, encargo, perfil o fundamentos históricos; since conserva vista actual o unchanged, sin delta.
- Instantánea original inmutable por ejecución; continuación de envío automático limitada a su preparación propia, terminada y vigente.
- Comprobación de todos los intentos anteriores inciertos antes de otro envío. Recibos tardíos y cancelaciones conservan efecto, material y permiso original.
- Requisitos relevantes de la oferta invalidan encaje, valoración y material; añadir webs de captación no invalida la solicitud.
- Captación con páginas y alcance explícitos, parciales/no soportados honestos y registro de revisiones manuales con propietario, fuente y pruebas.
- Fundamentos históricos recuperados del registro existente, sin una memoria paralela; archivos y paquetes anteriores preservados.
- Modelo, guía, plan y algoritmo incluidos en la edición genérica; identidad y procedencia compartidas entre portable y código público.
- Mejoras de presentación y advertencia de que las copias conservan datos guardados, no ediciones pendientes.

Este incremento no publica por sí mismo la aplicación ni acredita aceptación humana, búsquedas/envíos reales o ahorro medido. Consulta [LIMITES.md](LIMITES.md).

## Stubbs Jobs Beta 2 · 0.1.0-beta.2 · 01/10/2026

- Resumen y fichas distinguen trabajo guardado, actividad reciente e interrupciones sin confirmar.
- Comprobación obligatoria del portal antes de reintentar un envío; confirmaciones tardías sin repetir el formulario.
- Copias verificadas y recuperación aislada con permisos antiguos retirados y documentos conservados.
- Valoración de ofertas con fuentes, motivos y dudas; actualización al cambiar criterios o experiencia.
- Código de tareas y explicaciones separado, casos ficticios de calidad y comprobación repetible de versiones.
- Preparación inicial guiada: acceso a la carpeta, entrevista en el agente, borrador recuperable y confirmación del resumen antes de activar el perfil.
- CV opcionales y soporte para indicar primer empleo. Cambiar de chat conserva el avance y los documentos.
- Navegación con Mi perfil, Ofertas y Resumen; permisos decididos por oferta y seguimiento separado del envío real.
- Identidad visual con el gato Stubbs naranja, superficies neutras, temas claro y oscuro y tamaños adaptables.
- Versión identificable en Ayuda, documentación y archivos de entrega.
- Distribución portable vacía para Windows x64, documentación genérica y avisos de componentes incluidos.

Esta entrega incorpora las mejoras de continuidad de Beta 2 y conserva el flujo de preparación de Beta 1. No migra ni importa automáticamente datos de otra persona. Los formatos internos conservan sus versiones propias.

Consulta [LIMITES.md](LIMITES.md) para distinguir las verificaciones automáticas de las comprobaciones humanas aún pendientes.
