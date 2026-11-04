# Descubrimiento y priorización de ofertas

**Método vigente · 07/10/2026.** Aplica [system-design.md](system-design.md) a una búsqueda autorizada. [agent-guide.md](agent-guide.md) dirige la petición; [operations.md](operations.md) y [application-contract.md](application-contract.md) conservan las operaciones. Perfil y estrategia iniciales orientan; los datos confirmados actuales gobiernan.

## Qué debe producir una búsqueda

Oportunidades únicas que puedan mejorar la situación de la persona y conocimiento que permita decidir con menos reconstrucción. Cada resultado conserva qué se revisó, qué se concluyó, qué falta y qué paso merece atención.

Distinguir mínimos, valor del puesto, relación con experiencia, urgencia, incertidumbre y esfuerzo. No imponer profesión, país, moneda, salario o frecuencia históricos. La prioridad es consejo; no selecciona ni autoriza preparar, contactar o enviar.

## Orientación y alcance

Consulta agent-status y amplía perfil, antecedentes o casos pertinentes. Recupera criterios actuales, procesos existentes, exclusiones y duplicados. El indicador de antecedentes no reemplaza su contenido. Una búsqueda nueva no exige reabrir casos bloqueados sin información pertinente.

Cuando la petición identifica una estrategia, consulta `agent-status --search-profile ID`; en caso contrario usa la predeterminada. Para esa búsqueda autorizada, `plan --search-profile ID` o crear discovery con ese searchProfileId conserva su copia de criterios. Desde entonces `agent-status --request ID` es el ámbito de captación, incluido mínimo, moneda, fuentes, horario e indicaciones adicionales. Cambiar el predeterminado no redirige ese encargo ni sus reintentos. No utilizar el campo Horario para guardar cantidad de resultados, instrucciones de ejecución o permisos.

`followedSources` son empresas elegidas para ese perfil y se suman a los portales y a la lista de la instalación, que en una copia nueva está vacía. `sourceUrls` no vacío limita toda captación a esas webs y sustituye las fuentes iniciales; plataformas no permiten salir de ese alcance. Con fuentes vacías, usar las pertinentes para el perfil dentro de la petición. Un enlace de candidatura encontrado puede llevar al destino de esa misma oferta, sin habilitar búsquedas ajenas.

El encargo, inicio real, dueño y tanda siguen OPERACION. La lectura del método no inicia plan/refresh/handoff. Captación por correo retirada; la excepción de verificación de candidatura no es una fuente de empleo.

## Primera pasada: detectar sin reconstruir todo

Usar tools/scan_boards.py para captación pública autorizada y herramientas de navegador cuando correspondan. Leer alcance, método, páginas, cobertura, errores y último éxito. Acceso a portal, fuente configurada y listado recibido no acreditan revisión de todas sus vacantes. Con un perfil 100 % remoto, el captador omite los anuncios cuyo propio título o ubicación publican solo trabajo híbrido o presencial, con la misma lectura que los mínimos (16/10/2026); el silencio, un porcentaje de teletrabajo o una alternativa remota se conservan para revisión.

Con perfiles guardados, pasar `--request ID` al captador. Registrar apariciones de una vacante en varias búsquedas sin duplicar su candidatura ni copiar permisos. Su primera base de evaluación permanece hasta ui-criteria-scope explícito; ampliar por --case antes de valorarla o preparar material.

Antes de captar, revisar los anuncios pendientes de esa búsqueda (`pendingEntries` de `agent-status --request ID` y `agent-status --entries --search-profile ID`): promover los pertinentes con promote o cerrarlos con entry y motivo. Con el perfil predeterminado se incluyen también los anuncios sin perfil, anteriores a los perfiles: contrastarlos con todos los perfiles visibles antes de cerrarlos. Una entrada Nueva ya conocida no vuelve a aparecer como nueva en otra captación, así que dejarla sin revisar la oculta. Guardar hallazgos en Entradas mediante las operaciones oficiales. Comparar identidad de vacante, URLs y antecedentes antes de crear un caso nuevo. Alias de LinkedIn con el mismo ID numérico no crean otra oferta. Textos similares de intermediarios pueden ser un duplicado; sin identidad suficiente, conservar la duda.

Cribar por contenido del trabajo y criterios confirmados. Títulos, idiomas y etiquetas comerciales orientan, sin demostrar contrato, modalidad, país, requisitos o experiencia. Un requisito deseable ausente o una brecha técnica disminuyen el consejo de prioridad, no convierten por sí solos la oferta en incumplimiento de mínimos.

## Segunda pasada: la comprobación que cambia la decisión

Antes de abrir otra fuente, formular la duda decisiva y el paso que cambiaría con cada respuesta plausible. Comprobar primero mínimos explícitos, identidad/duplicado, valor real del trabajo y relación defendible con experiencia. Leer la publicación original de los casos pertinentes; no investigar exhaustivamente todos los agregadores.

| Pregunta | Comprobación suficiente y límite |
| --- | --- |
| ¿Hay incumplimiento mínimo explícito? | Condición publicada y evidence con fuente/fecha. El escritor aplica el mínimo vigente; no compensarlo con atractivo. |
| ¿Es el mismo proceso? | Identidad de vacante y destino; similitud sola conserva posible duplicado. |
| ¿Por qué merece atención? | Responsabilidad, crecimiento o condición concreta relacionados con objetivos actuales; sin porcentajes inventados. |
| ¿Qué experiencia puede defender la persona? | Requisito concreto y ejemplo confirmado; formación y proyectos conservan su naturaleza. |
| ¿Qué información falta ahora? | Duda que afecta a elegir o preparar; lo de otra fase puede seguir pendiente. |
| ¿Se puede reutilizar la investigación? | Mismo hecho, fuente y ámbito; conservar prueba/fecha originales y límites por caso. |

No repetir bloqueos sin información nueva. Cliente final desconocido puede afectar a una exclusión; no afirmar que está satisfecha. Preguntar a una empresa es contacto y requiere su permiso; investigar no lo concede.

## Condiciones, mínimos y elección

Mantener Sí, No, Pendiente y Contradicción con pruebas. Registrar el horario publicado en «Horario real» con proof: con `requiredSchedule`, un horario incompatible es incumplimiento de mínimos y su ausencia queda por concretar. Separar modalidad anunciada y contratación desde la zona buscada; contrato y jornada; salario publicado, fijo comprobado y respuesta personal para formularios; horario preferido y horario real.

Ausencia de sueldo, contrato o viajes no es cumplimiento ni incompatibilidad. Un híbrido/presencial explícito incumple 100 % remoto; contrato explícitamente incompatible incumple su criterio. Una banda fija que alcanza el mínimo permite negociar, sin confirmar fijo final; banda total con variable no acredita fijo. Conservar moneda y periodo, sin convertirlos por suposición.

`requirementMatch` compara por palabras el anuncio con las competencias confirmadas para ordenar la atención; no sustituye leer el anuncio ni cuenta como mínimo. Si no existe incumplimiento mínimo explícito, la oferta puede quedar Por decidir y elegirse aun con dudas técnicas o condiciones no publicadas. `ui-fit-review`.apply debe coincidir con esos mínimos; no se usa para bloquear por capacidad, años o A/B/C. Las preguntas de un formulario necesitan su significado y ámbito propios; el mínimo no se usa como sueldo deseado.

Antes de una candidatura, comprobar publicación, formulario, destino, material y permiso pertinentes. Elegir y preparar no acreditan envío ni condiciones para aceptar. Una enviada no se vuelve a preparar; comprobarla pertenece al seguimiento autorizado.

## Consejo de prioridad y valoración

La prioridad sigue una regla fija, para que dos agentes den el mismo resultado con los mismos datos. `agent-status` y `prepare` la devuelven como `suggestedPriority`, calculada desde `requirementMatch`:

| Encaje con las competencias confirmadas | Prioridad |
| --- | --- |
| `strong` | A |
| `partial` o `unknown` (sin requisitos legibles) | B |
| `weak` | C |

Usar `suggestedPriority` al promover o actualizar una oferta. Apartarse de ella solo con un motivo concreto y comprobable en `reason`, nunca por impresión general. La prioridad ordena la atención: no archiva por una brecha técnica, no selecciona ni autoriza.

Guardar ui-offer-assessment con assessmentFingerprint, reason, references, observedAt, unknowns y proof. `ui-fit-review` comprueba mínimos por su propia huella. Ninguna operación selecciona ni autoriza transmisión. `bestArgument` puede conservar un ejemplo defendible ligado a requisito/fuente; no garantiza éxito ni demuestra que esté en el CV enviado.

Preparar solo las ofertas elegidas con modo review/auto actual. Reutilizar respuestas y material válidos; no rehacer un CV por rutina ni inventar logros. Revisar ante cambios de dependencias, preservando los originales.

## Portales de empleo y fuentes agotadas · 21/10/2026

Las webs de empresa configuradas (captador) y los portales de empleo son fuentes distintas. Con `sourceUrls` vacío, `agent-status --request ID` de una búsqueda (y `--search-profile ID`) devuelve:

- **portalPlans:** una consulta individual por cada puesto breve del perfil en LinkedIn, Indeed, InfoJobs y Tecnoempleo, más Wellfound cuando se busca remoto. `filtersApplied` indica parámetros pedidos por el enlace, no confirma que la página los haya aplicado; comprobar palabras, zona, remoto y fecha en la página. La ventana solo se acorta tras revisar todos los planes de ese perfil y criterios sin incidencias; una ronda parcial conserva la ventana amplia. Registrar cada portal con `ui-source-review` (sourceUrl del plan, alcance y resultado reales). En Wellfound, comprobar contratación remota desde el país buscado y conservar anuncios sin salario si se usa un filtro salarial. Con un perfil redactado como frase, sin puestos breves, `available` es false: proponer puestos concretos sin inventarlos.
- **discoveryYield:** cuenta solo rondas seguidas del mismo perfil y criterios en las que todas las webs de empresa configuradas y activas se captaron correctamente sin añadir ofertas. Una web omitida, bloqueada o parcial no acredita agotamiento. `sourcesExhausted` y `skipScanner` se refieren solo a esas webs, no al mercado ni a los portales. Con `skipScanner`, no repetir el captador de esas webs durante 24 horas; continuar los planes de portal pendientes y registrar su cobertura propia.
- **sourceStats:** ofertas, envíos y descartes de cada web de empresa configurada. `lowYield` señala una web con muchas ofertas, casi ningún envío y la mayoría descartadas por la persona. Solo la persona decide dejar de revisarla (en Lo que busco o pidiéndolo expresamente: `ui-source-toggle` con sourceId, enabled y expected); el captador deja de recorrerla y sus ofertas e historial se conservan.

## Catálogo de portales · 04/11/2026

`plans` devuelve planes por puesto de los portales principales y, en `morePortals`, los demás de la zona, sin obligación de completarlos: úsalos cuando los principales se agoten. Respeta `excludedPortals`: esos portales no se usan. `sourceUrls` sustituye a todo lo demás. Si propones una fuente nueva con buenos resultados, dilo en el resumen.

## Cerrar la búsqueda dejando un punto de continuación

Conservar fuentes realmente comprobadas, fecha, alcance, pendientes, incidencias y recuento acreditado desde el inicio. Registrar revisión manual mediante ui-source-review dentro de discovery running propio. El resultado combina captador y navegador sin borrar intentos anteriores ni reescribir cobertura antigua.

“No encontrado” significa no encontrado en esas fuentes, alcance y fecha. Paginación sin acreditar, formato no soportado, fallo, sesión caducada y búsqueda parcial mantienen su límite. Sin base guardada, no llamar nuevas a preselecciones históricas.

Una nota independiente va a ui-offer-note; requisitos y condiciones conservan sus operaciones y huellas. Guardar la conclusión que permitirá no repetir trabajo, con fundamento y condición de revisión. No copiar toda la web ni mantener otra lista operativa de empresas o tareas.

Terminar al alcanzar el resultado del encargo, encontrar el impedimento concreto o no poder cambiar la decisión con más lectura. Conservar lo parcial y continuar los IDs independientes autorizados. No fijar cuotas de candidaturas ni investigaciones; un presupuesto orienta atención sin suprimir comprobaciones obligatorias.

Recuentos y tiempo realmente medidos permiten evaluar trabajo, no causalidad ni probabilidad de contratación. Los análisis avanzados, experimentos, programación y contactos requieren su petición. La siguiente búsqueda o comprobación nunca nace solo de la antigüedad.
