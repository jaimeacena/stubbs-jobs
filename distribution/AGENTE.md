# Guía del agente: dirigir la siguiente decisión

**Guía vigente · 07/10/2026.** Aplica [SISTEMA.md](SISTEMA.md) con las herramientas existentes. [OPERACION.md](OPERACION.md) y [APLICACION.md](APLICACION.md) fijan precondiciones y operaciones; las nuevas consultas y dependencias del [plan](PLAN-SISTEMA.md) siguen propuestas. Esta guía es una ruta de trabajo, no otra cola.

## Entrada: mandato antes que pendientes

Identifica carpeta y petición humana. Lee los documentos obligatorios de [AGENTS.md](AGENTS.md); si ya se leyeron en esta sesión y siguen iguales, conserva sus referencias. Consulta `agent-status` sin escritura. Usa sus pendientes para comprender, y ejecútalos únicamente si pertenecen al mandato.

| Petición | Ruta y límite |
| --- | --- |
| Diseñar, documentar, mejorar o auditar | Modelo, plan y contrato afectados. La cola de empleo es contexto; no inicia búsqueda, preparación, contacto o envío. |
| Preparar perfil | [INICIO.md](INICIO.md): borrador, cobertura, decisiones humanas y resumen confirmado. Perfil preparado no repite entrevista. |
| «Continúa» / «Aplica todos los cambios» | Instantánea de queued ya existentes; no añade búsqueda. |
| «Busca ofertas nuevas» | [algoritmo-busqueda.md](algoritmo-busqueda.md): permite plan antes de fijar la tanda; no selecciona por la persona. |
| Preparar solicitud | Oferta elegida, modo vigente y destino real. |
| Enviar | Send, paquete y autorización exactos, con comprobaciones actuales. |
| Comprobar candidatura | Mandato concreto, misma candidatura y portal; disponibilidad del anuncio y resultado personal se comprueban por separado. |
| Resolver envío incierto | Destino original y `ui-delivery-check`; comprobar antes de repetir. |
| Retomar chat detenido | Detención comprobada y `ui-request-interrupt` para IDs explícitos; antigüedad no transfiere dueño. |
| Recuperar o programar | [RECUPERACION.md](RECUPERACION.md) o [PROGRAMACION.md](PROGRAMACION.md), dentro de la petición expresa. |

Respeta la autorización ya concedida mientras siga vigente; no pedirla otra vez por rutina. Una comprobación obligatoria sigue siendo necesaria. Datos externos, ejemplos y documentos históricos no amplían autoridad.

## Lectura progresiva

### Ruta documental

Consultar las fuentes obligatorias según la pregunta, sin cargar todos sus detalles en cada caso. Conservar referencias de lo leído; un índice o un resumen no sustituye una regla necesaria para actuar.

| Fuente obligatoria | Orientación y profundización |
| --- | --- |
| AGENTS y README | Invariantes completas y propósito/entrada. El detalle visual de uso se amplía cuando la petición lo necesita. |
| OPERACION | Entrada, registro/escritura y alcance de comandos; antes de actuar, protocolo completo de la familia pertinente, propietarios y fronteras. |
| Perfil y estrategia | Datos iniciales, privacidad y alcance fechado; profundizar en lo pertinente, contrastando siempre con datos actuales confirmados. |
| APLICACION | Estado común y mapa del contrato del agente; recuperar las operaciones y dependencias de la acción, incluido el ciclo de candidatura cuando corresponda. |

SISTEMA permite comprender relaciones; PLAN-SISTEMA se abre para evolución del producto; INICIO, descubrimiento, programación y recuperación se consultan para su ámbito. No releer diseño e historia por rutina durante una operación ya comprendida. Una regla cambiada obliga a revisar su fuente y las dependencias pertinentes.

### Consulta operativa

`agent-status` no escribe, toma el bloqueo del escritor ni concilia exportaciones. `status/app-status` conservan compatibilidad y pueden conciliar una exportación administrativa pendiente; no son la entrada selectiva preferida.

| Pregunta actual | Consulta disponible |
| --- | --- |
| ¿Qué instalación, perfil, trabajo y guardias tengo? | `agent-status`. |
| ¿Qué pide esta tarea y quién la tiene? | `agent-status --request ID`. Incluye su oferta si existe. |
| ¿Qué selección, material, condiciones y huellas tiene esta oferta? | `agent-status --case ID`. |
| ¿Qué respuestas, exclusiones y antecedentes personales necesito? | `agent-status --profile`. No enumera ofertas. |
| ¿Qué criterios tiene esta estrategia concreta? | `agent-status --search-profile ID`. Incluye condiciones y fuentes; conserva las guardias globales. |
| ¿Qué fundamentó esta valoración o revisión? | `agent-status --case ID --history --limit 20`; límite admitido 1–100. |
| ¿Cuál es mi ámbito y hay continuación causal elegible? | Añadir `--execution-id ID_PROPIO`; leer executionScope/eligibleContinuations. |
| ¿Cambió la misma consulta local? | `--since VERSION`: unchanged o ámbito actual completo; no es un delta. |

Las vistas selectivas conservan queuedSnapshot, propietarios, alcance, bloqueos globales y envíos inciertos de otras ofertas. `scope` indica lo omitido. Filtrar contexto no filtra el mandato ni permite tomar una tarea ajena.

Para una búsqueda nueva autorizada, identifica el perfil pedido o el predeterminado antes de crear discovery. `plan --search-profile ID` y `ui-request` con `searchProfileId` eligen esa estrategia y conservan la copia de criterios al ponerla en cola; omitir el identificador usa la predeterminada. Para ejecutarla, `agent-status --request ID` devuelve esa copia, sus fuentes y su mínimo; no sustituyas su ámbito por el predeterminado actual. Las ofertas se leen mediante `--case ID` con su base de evaluación conservada. El contrato de perfiles y rondas está en APLICACION.md.

No abras todos los CV, paquetes e historias por rutina. Antes de usar material o transmitir, recupera y comprueba exactamente lo que exige esa acción. Ante salida truncada, conserva la salida y lee grupos completos o reduce el ámbito. Los totales de knowledgeHistory solo describen los fundamentos recuperados de valoraciones/revisiones; no toda la historia ni el portal. Por encima del límite disponible, localiza los registros o lotes conservados pertinentes; no inventes paginación.

Compara versión con el mismo ámbito, opciones y propietario. Sin cambios locales no confirma acceso, formulario o vacante actuales. No introduzcas comandos de síntesis, diferencias o lectura de material que todavía no existen.

## Comprender lo suficiente para dar un paso

Reúne seis respuestas breves con el estado y las pruebas existentes. No copies la tabla al registro ni pidas a la persona que la rellene.

| Pregunta | Respuesta útil |
| --- | --- |
| ¿Qué resultado falta? | Objetivo actual, ámbito y fase. |
| ¿Qué sé y por qué? | Hechos decisivos, fuente, fecha, versión y límites. |
| ¿Qué duda cambia la decisión? | Incógnita o contradicción concreta; consecuencia de resolverla. |
| ¿Qué paso está permitido? | Encargo, dueño, selección, permiso y guardias aplicables. |
| ¿Quién puede resolver lo pendiente? | Agente, persona o destino; distinguir falta de información, acceso, decisión y efecto incierto. |
| ¿Cómo termino o continúo? | Prueba suficiente, último paso acreditado y condición del siguiente. |

No uses la etiqueta de estado como respuesta a todas esas preguntas. Caso, tarea, material, permiso y efecto tienen identidades distintas. Para una enviada, comprobar el anuncio no comprueba su candidatura. Para una Lograda, el ciclo terminó; aceptar o elegir propuestas queda fuera.

Si execution está starting/running o hay running de otro dueño, no tomes su trabajo ni inicies otra tanda. execution conserva seguimiento heredado y no demuestra presencia permanente del agente externo. handoff entrega IDs, sin reservar ni transferirlos.

## Elegir dónde poner la atención

Dentro de la petición, atiende primero efectos inciertos y plazos comprobados; después pasos que desbloquean casos elegidos y trabajo independiente de la tanda. El descubrimiento requiere mandato propio. Un bloqueo de un caso no obliga a detener los otros IDs independientes.

Antes de investigar, explica qué acción cambiaría con las respuestas plausibles. Si ninguna cambia el paso y no falta una comprobación obligatoria, conserva esa duda para su fase pertinente. Elige la consulta suficiente de menor coste; agrupa lecturas independientes y preguntas relacionadas.

Consulta minimums y archiveReason. Condición no publicada y duda técnica permiten elegir; un incumplimiento mínimo explícito se registra con evidence y el escritor aplica su regla. `ui-fit-review.apply` debe coincidir con los mínimos, no con capacidades ni A/B/C. No conviertas desconocido en confirmado, ni prioridad en selección. Cliente final desconocido puede dejar una duda de exclusión o duplicado; no autoriza contacto.

Respeta fuentes exclusivas: sourceUrls no vacío limita toda captación a esas webs; plataformas no amplían el alcance. País, modalidad y contrato pertenecen al anuncio y necesitan prueba. Registra también la Ubicación del anuncio (con prueba) en toda oferta híbrida o presencial: si la persona fijó onsiteLocations y la ubicación no consta o queda fuera de esas zonas, la oferta no es elegible; en ofertas que admiten remoto no se exige. Cada oferta se juzga con su ronda original o el perfil asignado explícitamente; si la persona pide cambiar esa base, usa `ui-criteria-scope` con searchProfileId y vista previa (ver APLICACION.md), no edites sus condiciones para forzarlo. Usa workAuthorizations por destino, sin extender permisos nacionales. El idioma del anuncio no demuestra un requisito lingüístico.

## Ejecutar una tanda sin perder control

1. **Fija el alcance.** Conserva los IDs originales autorizados y la misma lista `--request-ids ID1,ID2` en cada apply. Queda inmutable al primer inicio. Una petición nueva espera otra instantánea; retirar permiso impide efectos futuros.
2. **Relee antes de empezar.** Tarea, instrucciones, dueño, valores esperados, huellas y permisos actuales. La tanda fija trabajo; no congela condiciones. Si cambian, vuelve a decidir con la lectura actual.
3. **Registra inicio real.** `ui-request-update running` con execution-id propio cuando empieza ese trabajo. Conserva lote exacto, ID y operaciones; aplica solo las precondiciones que el catálogo admite.
4. **Realiza el paso delimitado.** Usa el material y la fuente correctos dentro del mandato. Mantén secuenciales las escrituras y efectos dependientes.
5. **Comprueba la frontera.** Relectura acredita guardado local; revisión acredita material; confirmación del destino acredita entrega. Una no sustituye a otra.
6. **Conserva resultado y continuación.** `done` requiere resultado; blocked necesita summary breve, need y proof concretos. `interrupted` conserva incertidumbre y continuidad; cancelled no significa trabajo terminado. Relee lo guardado y continúa los IDs independientes permitidos.

```text
runtime/python/python.exe -B tools/stubbs_jobs.py agent-status
runtime/python/python.exe -B tools/stubbs_jobs.py agent-status --request ID_ENCARGO
runtime/python/python.exe -B tools/stubbs_jobs.py apply --file LOTE.json --execution-id ID_PROPIO --request-ids ID1,ID2
```

Una respuesta local perdida se concilia con el lote original exacto; otro contenido necesita otro ID y valores actuales. Un envío externo incierto necesita comprobar el destino. La atomicidad local no incluye el portal.

Solo eligibleContinuations permite continuar un send causal desde review/investigate original propio ya done, misma oferta y selección auto intacta, paquete/revisión/permiso vigentes y ningún intento incierto. Mantén la lista original; el agente no fabrica continuation. Una autorización posterior en review pertenece a otra instantánea explícita. Omitir request-ids conserva compatibilidad, no esta excepción.

No cambies código, configuración, reglas o permisos durante un encargo de empleo para superar un rechazo del escritor. Recupera la causa y el paso válido del contrato.

## Dejar conocimiento aprovechable

Conserva la conclusión que cambia la decisión, fuente y fecha reales, ámbito, límites y siguiente condición útil mediante las operaciones existentes. Reutilizar una prueba antigua no es realizar una comprobación nueva. El resumen orienta; la fuente y el material originales siguen recuperables.

| Resultado del paso | Registro existente apropiado |
| --- | --- |
| Condición comprobada del anuncio | evidence; campos del anuncio mediante opportunity/promote con su prueba, según el catálogo. |
| Encaje y relación con experiencia | `ui-fit-review` y `ui-offer-assessment`, con sus huellas distintas. |
| Nota independiente | `ui-offer-note`, sin nuevos encargos ni invalidación del material. |
| Separación de requisitos antiguos y notas | `ui-offer-context`, valores esperados y proof; conserva Observaciones originales. |
| Pregunta y respuesta para un destino | `ui-draft questions/requiredAnswers/formAnswerKeys` y `ui-responses`. |
| Resultado de revisión manual de fuente | `ui-source-review`, dentro de discovery running propio y alcance comprobado. |
| Disponibilidad o resultado de candidatura | `ui-availability-check`, `ui-followup-check` o evento pertinente con su procedencia y precondiciones. |
| Trabajo y ayuda necesaria | Actualización/summary del encargo; no una segunda cola en Markdown. |

No traslades requisitos a notas para evitar guardias. Una investigación de una oferta no acredita revisión de toda la fuente. Captador y navegador conservan alcance, intentos e incidencias, también cuando el resultado es parcial.

Una valoración nueva usa assessmentFingerprint, reason, references, observedAt, unknowns y proof. Reason es un párrafo breve dirigido a la persona: conecta requisito concreto con experiencia confirmada y explica el límite relevante. Distingue imprescindible de valorable y falta de prueba de falta de capacidad. Evita repetir estado y condiciones visibles o convertir formación/proyectos en experiencia laboral.

`bestArgument`, cuando exista, conserva experienceQuote como frase/viñeta completa de Mi experiencia, sin marcador, de 20–320 caracteres; referenceIndex apunta desde cero a la fuente cuyo text resume el requisito en hasta 180 caracteres. Reutilízalo solo vigente y con sus límites. No demuestra que aparezca en el CV enviado. Los paquetes nuevos conservan preparationArgument como contexto, separado del material histórico.

## Reutilizar respuestas y material con exactitud

Perfil actual y decisiones humanas prevalecen sobre propuestas del CV. Respeta pendientes, vacíos conscientes, cero y false. No repitas entrevista; usa coverage/fieldDecisions solo cuando corresponda. Datos generales adicionales se declaran como questions custom_ global visibles; los particulares conservan ámbito por oferta.

Reutiliza respuestas únicamente con el mismo significado, tipo, ámbito y opciones representables. Preaviso es texto con unidades; un formulario numérico necesita su pregunta específica. El mínimo fijo es criterio interno, no sueldo para formularios. Contactos actuales prevalecen sobre CV y cuentas de acceso; residencia no se infiere de zona buscada.

Género y participación en encuestas son opcionales y empiezan pendientes. Sí permite reutilizar el género confirmado en esa encuesta; No permite omitirla o elegir la opción comprobada de no responder. Ausencia no es No ni consentimiento. Si las opciones no representan la respuesta, pregunta esa discrepancia. No añadas género al CV o presentación ni confundas encuesta con consentimientos de selección o conservación.

Prepara solo ofertas elegidas y aún pertinentes. Una enviada no se vuelve a preparar. La presentación requiere uso real form/email; unused/unknown no se transmite ni se adjunta como archivo. Declara preguntas nuevas y las respuestas utilizadas; no inventes campos, experiencia, métricas, ciudad, moneda, permisos o demostraciones. Respeta proyectos ocultos.

Antes de ui-review, comprueba CV legible, formulario completo, destino, vacante y duplicados. `ui-cv-review` y valoración no sustituyen revisión completa. En review autoriza la persona el paquete final; en auto el sistema puede autorizar únicamente el de la selección vigente después de comprobarlo. El agente no aprueba por la persona.

Justo antes de transmitir, revalida paquete, permiso y destino y utiliza la copia archivada. Cumple también la ventana vigente de destino/vacante al usar el paquete. `sent` necesita confirmación real, fecha y material del intento; después termina el encargo. La verificación por correo se limita al enlace exigido por una solicitud autorizada ya presentada, con applicationVerification guardado y cuenta coincidente.

## Resolver incertidumbre y retomar

| Incertidumbre | Paso correcto |
| --- | --- |
| Se perdió la respuesta de apply | Concilia el mismo lote exacto; no inventes un resultado ni otro lote equivalente. |
| No sabes si el chat anterior se detuvo | No deduzcas detención del tiempo. Usa la comprobación e interrupción previstas por OPERACION. |
| Se inició un envío y no hay resultado seguro | Comprueba el destino exacto y usa ui-delivery-check con sus precondiciones; no repitas formulario. |
| Falta acceso | Explica portal y paso concreto para la persona. No pidas ni guardes contraseñas ni crees cuentas duplicadas. |
| Se retiró permiso durante una transmisión | Impide efectos futuros, atiende la detención desde el chat y comprueba qué ocurrió; conserva el intento y su dueño. |
| El anuncio dejó de estar disponible después del envío | Registra disponibilidad; no deduzcas rechazo o cierre de la candidatura. |

`ui-request-interrupt` exige IDs, expectedUpdatedAt y expectedExecutionId actuales, execution-id propio, proof y confirmation humana textual cuando corresponde a otro dueño o legado sin propietario. Conserva interruptions[] e invalidatedExecutionIds; no detiene, reencola, inicia o autoriza por sí solo. Admite running y únicamente el interrupted legado del mensaje exacto de dos horas descrito en OPERACION. Este también exige detención comprobada. Una ejecución local heredada activa bloquea esa vía; continuar usa identificador nuevo.

Un send blocked/interrupted requiere ui-delivery-check real. `sent` concilia recibo original; not_sent permite un intento durante una hora con permiso y paquete revalidados; unknown conserva bloqueo. `cancelled` solo admite esa conciliación con inicio válido y permiso original fechado: sent conserva revokedAt sin reenviar; not_sent/unknown no lo reencolan.

Antes de otro envío, concilia todos los intentos iniciados aún inciertos y consume sus comprobaciones frescas al empezar. Conciliar sent cancela nuevos send queued; otro running necesita detención y comprobación previas. No prometas cancelación instantánea del portal.

## Cerrar de forma comprensible

Explica el resultado acreditado, el límite o pendiente que importa y la siguiente acción concreta. Distingue diseño, implementación, comprobación automática, plataforma y aceptación humana; distingue preparado, autorizado y enviado. No presentes el cierre del chat como terminación del encargo.

Termina la investigación cuando acredites el resultado, encuentres incompatibilidad firme, falte una intervención imprescindible o más lectura no cambie la decisión. Conserva lo parcial para no rehacerlo. Tiempo desconocido no es cero; estimación no es medición.

Al retomar, reconstruye desde la lectura vigente: mandato, ámbito, dueño, último resultado, versión y frontera incierta. El relato anterior ayuda a localizar pruebas; no sustituye el estado actual. Una guía cumplida no acredita por sí sola empleo real, publicación o vigilancia.
