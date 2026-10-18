# Notas de cambios

## Sin publicar · Horario confirmado y CV adaptado · 18/10/2026

- **Horario obligatorio confirmado:** si un perfil exige horario (por ejemplo, solo de mañana), una oferta cuyo anuncio no lo confirma (no lo publica, dice «flexible» o solo habla del verano) se descarta automáticamente con el motivo «El anuncio no confirma tu horario obligatorio». Vuelve sola a Por decidir cuando se registra un horario compatible. Antes quedaba «Por confirmar» y se podía elegir y enviar. La columna Horario distingue «Sin confirmar» de «No cumple». Las solicitudes ya enviadas no cambian.
- Al descartarse automáticamente una oferta, sus tareas pendientes se cancelan en el mismo momento, en vez de esperar a la siguiente acción.
- **CV adaptado o justificado:** antes de dar por revisada una solicitud, el agente debe indicar si el CV se adaptó a esa oferta (un PDF propio que no use otra oferta) o si reutiliza el CV general, y explicar por qué. La pantalla «Revisar solicitud» lo muestra («Adaptado a esta oferta» o «CV general, sin adaptar a esta oferta») junto con el motivo, que antes no se veía en ningún sitio.
- **CV adaptado con un comando:** `build-cv` prepara un CV de una página en español o inglés para cada oferta con los datos de tu perfil confirmado, elegidos y ordenados según el anuncio. Rechaza cualquier habilidad, herramienta, cifra o puesto que no conste en tu perfil y no usa proyectos ocultos. Cada oferta recibe su propio PDF, que aparece en Currículums y como CV de esa solicitud. Antes no había forma oficial de hacerlo y las solicitudes salían con el CV general.
- Documentación del agente sincronizada entre la edición personal y la pública (frases duplicadas, notas del 17/10 y nombre del CV adjunto).

## Sin publicar · Revisión de búsqueda y solicitudes · 16/10/2026

- **Arreglo urgente:** los perfiles de búsqueda guardados antes de añadir «Horario obligatorio» impedían abrir `agent-status` («Hay un perfil de búsqueda incompleto o duplicado»). Ahora se leen como «Sin requisito» y se completan sin perder nada.
- Los anuncios captados antes de existir los perfiles de búsqueda (154 en una instalación real) ya no quedan sin revisar para siempre: pertenecen al perfil predeterminado, cuya próxima búsqueda los revisa contrastándolos con todos los perfiles.
- Pedir una búsqueda después de cambiar los criterios de un perfil sustituye a la que seguía en cola sin empezar con los criterios anteriores, en vez de dejar dos búsquedas pendientes.
- Con un perfil 100 % remoto, el captador deja fuera los anuncios que en su propio título o ubicación dicen solo «Híbrido» o «Presencial» (78 de 267 en una instalación real); los que mencionan una opción remota o no lo dicen siguen llegando.
- El captador reconoce más países y ciudades (Portugal, Francia, Alemania, Países Bajos, Irlanda, Italia, Bélgica… y muchas ciudades españolas), respeta zonas como «Unión Europea» o «Anywhere» y no descarta una lista mixta como «Bilbao; Lisboa».
- Ofertas recuerda bajo el título la búsqueda guardada o en curso, y Resumen indica con qué perfil se buscará y permite «Cancelar búsqueda» antes de que empiece.
- La tarea que crea «Solicitar con revisión» se llama «Preparar solicitud», como la ficha («En preparación»), en lugar de «Comprobar solicitud».
- Modalidad más fiel al anuncio: «Semi-remoto», «Semipresencial», «Teletrabajo parcial», «Remoto 2 días a la semana» o «Remoto con 2 días presenciales» cuentan como híbrido y ya no pasan por 100 % remoto. Las visitas al mes o al año siguen siendo una cuestión de viajes, y una alternativa real («Remoto o semipresencial») se conserva.
- El captador reconoce femeninos en -a de puestos en -e («Dependiente» ↔ «Dependienta», «Asistente» ↔ «Asistenta») y lee por separado los puestos unidos con «y»/«o» dentro de una frase («Auxiliar administrativo junior y puestos de recepción»), sin convertir una palabra suelta en un puesto.
- El captador lee también las webs de empleo de empresas en Lever (también la región UE), Workable, Personio, SmartRecruiters y Recruitee: al añadir en «Webs» su dirección (jobs.lever.co/empresa, apply.workable.com/empresa, empresa.jobs.personio.de, jobs.smartrecruiters.com/Empresa, empresa.recruitee.com) obtiene el listado completo de su API pública, recorre las páginas hasta comprobar el final y marca como parcial cualquier página o total sin acreditar. Cada vacante conserva una identidad estable en ese portal, y la web exclusiva sigue limitada a esa empresa. Antes quedaban como cobertura parcial sin vacantes.
- Tras iniciar sesión o completar una verificación del portal que bloqueaba al agente, **Ya he completado el acceso** en la ficha devuelve esa tarea a la cola en un paso. No se ofrece para envíos inciertos, que siguen necesitando comprobar el portal.
- La prioridad A/B/C ordena, pero ya no impide que la planificación prepare una oferta elegida.
- Acciones más rápidas: cada acción devuelve el mismo estado breve que la actualización periódica, en lugar del estado completo. Con 99 ofertas reales, la respuesta baja de 5 MB a alrededor de 1 MB.
- Actualización del estado más ligera: la vista breve que piden la actualización periódica y cada acción solo prepara el detalle (borradores, respuestas, material enviado, evidencias e historial) de las ofertas que tienes abiertas, y la comprobación de los paquetes conservados evita resoluciones de ruta innecesarias en Windows. Con 99 ofertas reales, preparar el estado breve baja de unos 0,8 s a 0,4 s y el completo de 1,1 s a 0,6 s, con el mismo resultado.
- Resumen y los avisos de la ficha indican cómo iniciar las tareas guardadas («Continúa con Stubbs Jobs»), también tras autorizar un envío, pedir una comprobación o reintentar.
- El servidor local responde con su mensaje de error aunque una petición rechazada no se haya leído entera; en Windows antes se cortaba la conexión.

## Sin publicar · Preparación para más perfiles · 14/10/2026

- El agente consume mucho menos contexto: `agent-status` lista por páginas de 20 las ofertas abiertas (primero las que tienen encargos o cambios pendientes), deja descartadas y cerradas para `--offers closed|all`, abrevia pruebas largas y, con más de 50 encargos en cola, conserva todos los IDs sin repetir su detalle. Con 66 ofertas reales pasa de 233 KB a 81 KB, y deja de crecer con el historial.
- Lectura obligatoria más corta: AGENTS.md y CLAUDE.md indican qué secciones de la guía, la operación y el contrato leer según la petición, sin cargar el contrato completo por rutina.
- Guardados mucho más rápidos con muchas ofertas: añadir 100 ofertas con 1.000 ya registradas baja de 73 s a 14 s.
- Condiciones con nombres neutros para cualquier país: el agente ve y puede usar «Cumple modalidad», «Cumple contrato», «Cumple viajes» y «Cumple salario mínimo»; los registros existentes conservan sus claves.
- Aviso sobre las condiciones de los portales: Auto-solicitud, el README, el manual y AGENTS.md explican que muchos portales prohíben el uso automatizado y cómo evitar el riesgo.
- Captador automático válido para cualquier profesión: reconoce «Enfermero/a», «(a)», plurales y equivalentes en inglés de profesiones comunes («Camarera» ↔ «Waiter», «Contable» ↔ «Accountant»), sin abrir puestos no relacionados.
- Historial del registro acotado: se conservan las 100 copias más recientes y una por día durante 90 días; nunca se retira una copia citada por el registro ni una copia en conflicto.
- Vistas más rápidas con muchas ofertas: con 660 ofertas ficticias, la preparación del estado baja de 6,4 s a 1,4 s.
- Zona horaria de la persona en plazos y «Hoy»; la modalidad se describe frente a tu preferencia («Cumple tu modalidad») en lugar de «Remoto desde España».
- Aviso cuando la carpeta está dentro de OneDrive, Dropbox u otro servicio de sincronización.
- Guía de inicio para personas no técnicas: qué agente usar, aviso de Windows sin firma, desbloqueo del ZIP y carpeta local. Preparación del perfil con menos lectura obligatoria para el agente y ayuda para salarios mensuales o por horas.
- La construcción de la descarga y del código público se detiene si encuentra datos personales de la instalación; las sustituciones personales viven en private/.
- Guía de contribución, política de seguridad y plantillas de incidencias para GitHub.

## Sin publicar · Reorganización documental · 14/10/2026

- Presentación en inglés y español, guías en docs/ con nombres en inglés e índice de lectura.
- Documentos personales separados en private/, fuera de Git y de los insumos de construcción; compatibilidad de lectura y recuperación con nombres anteriores.
- Enlaces, instrucciones de inicio y constructores de descarga/código actualizados. Comprobación de enlaces locales integrada en el control de calidad.

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

Las comprobaciones de esta entrega se detallan en [limits.md](docs/limits.md). Los ejemplos visuales son ficticios; no acreditan trabajo real ni aceptación humana.

## Stubbs Jobs Beta 3 · 0.1.0-beta.3 · 02/10/2026

- Consulta del agente sin escritura, contexto breve y ampliación por oferta, encargo, perfil o fundamentos históricos; since conserva vista actual o unchanged, sin delta.
- Instantánea original inmutable por ejecución; continuación de envío automático limitada a su preparación propia, terminada y vigente.
- Comprobación de todos los intentos anteriores inciertos antes de otro envío. Recibos tardíos y cancelaciones conservan efecto, material y permiso original.
- Requisitos relevantes de la oferta invalidan encaje, valoración y material; añadir webs de captación no invalida la solicitud.
- Captación con páginas y alcance explícitos, parciales/no soportados honestos y registro de revisiones manuales con propietario, fuente y pruebas.
- Fundamentos históricos recuperados del registro existente, sin una memoria paralela; archivos y paquetes anteriores preservados.
- Modelo, guía, plan y algoritmo incluidos en la edición genérica; identidad y procedencia compartidas entre portable y código público.
- Mejoras de presentación y advertencia de que las copias conservan datos guardados, no ediciones pendientes.

Este incremento no publica por sí mismo la aplicación ni acredita aceptación humana, búsquedas/envíos reales o ahorro medido. Consulta [limits.md](docs/limits.md).

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

Consulta [limits.md](docs/limits.md) para distinguir las verificaciones automáticas de las comprobaciones humanas aún pendientes.
