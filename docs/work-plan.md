# Plan de evolución del sistema

**Plan vigente.** Desarrolla [system-design.md](system-design.md) mediante recorridos completos y conserva [agent-guide.md](agent-guide.md), [operations.md](operations.md) y [application-contract.md](application-contract.md). Las reglas de lo ya entregado están en el contrato y los límites públicos en [limits.md](limits.md). Este plan no autoriza búsquedas de empleo ni candidaturas.

## Decisiones abiertas

- **Base de datos, aplazada:** `data/registry.json` sigue siendo el registro operativo. Reabrir si guardar supera 2 s de forma sostenida o el registro pasa de 100 MB.
- **Límite conocido del encaje:** compara palabras y no entiende equivalencias no listadas.
- **Sin acreditar:** aceptación humana de lo entregado, lector de pantalla, otro ordenador y resultados en portales reales.

## Resultado buscado

Un agente debe reconstruir la situación pertinente, decidir el siguiente paso permitido, recuperar su fundamento y continuar sin duplicar trabajo o efectos. Cada paso deja conocimiento útil y una continuación comprobable. La persona recibe resultados claros y preguntas únicamente cuando su intervención hace falta.

La prioridad es **reducir la reconstrucción necesaria para la siguiente decisión correcta**. Primero conservar precisión, autoridad, propiedad y efectos; después reducir el coste completo de leer, actuar, comprobar y retomar. La interfaz y el agente comparten significado, con distinto detalle.

La torre ordena responsabilidades; este plan ordena dependencias y evidencia. Los IDs D0–D5 conservan continuidad con el plan anterior. Los detalles actuales de presentación pertenecen a APLICACION; las comprobaciones fechadas pertenecen a su registro de validación. No hay otra lista de encargos operativos en este documento.

## Diagnóstico de la lectura actual

| Fricción observada en documentos o código | Consecuencia | Respuesta propuesta |
| --- | --- | --- |
| Modelo y plan combinaban reglas vigentes con añadidos de fechas sucesivas. | El agente debe resolver qué versión de una frase sigue aplicándose. | Consolidar presente y enlazar contrato, propuesta y evidencia; conservar antecedentes fuera de la ruta principal. |
| La consulta selectiva filtra ofertas, pero puede repetir contexto y material extenso. | Truncamiento o varias lecturas para entender un caso pequeño. | Orientación suficiente, referencias a detalle y omisiones declaradas. |
| El siguiente paso se reconstruye desde tareas, condiciones, permisos y material. | Riesgo de confundir falta de información, acceso, decisión o efecto. | Situación derivada que explique cada impedimento y su responsable. |
| Historia y huellas no ofrecen dependencias uniformes. | Cuesta determinar qué sigue siendo reutilizable después de un cambio. | Exponer primero los ámbitos actuales; afinar solo una dependencia cuyo coste se demuestre. |
| Continuar requiere relacionar dueño, versión, interrupciones y comprobaciones. | Puede repetirse trabajo o perderse la frontera todavía incierta. | Mostrar la continuación derivada antes de crear nuevas entidades. |
| Una salida corta no mide el coste de producirla, ampliarla y verificarla. | Ahorro aparente que desplaza esfuerzo a otras llamadas o al siguiente chat. | Medir el recorrido completo y su exactitud. |

Estas observaciones no son porcentajes medidos de eficiencia ni fallos acreditados de una candidatura real. El plan requiere una línea base ficticia reproducible antes de prometer mejoras de rendimiento.

## Capacidad presente y evolución pendiente

| Capacidad existente | Ancla y límite actual | Evolución pendiente |
| --- | --- | --- |
| Registro único, escritor y conservación | Lotes idempotentes, guardias por operación, originales y paquetes. Atomicidad local, no del portal. | Mantener integridad y compatibilidad; no añadir otro almacén. |
| Entrevista progresiva | Coverage, fieldDecisions, borrador y resumen confirmado. `optionalPending` no impide la preparación suficiente; perfil preparado no repite entrevista. | Evaluación de comprensión y carga con personas nuevas. |
| Consulta del agente | `agent-status` puro, case/request/profile/history, scope y guardias globales. `--since` devuelve vista completa o unchanged. | Síntesis uniforme, detalle por referencia y diferencias pertinentes. |
| Mínimos y valoración | Mínimos separados de capacidad/prioridad; assessment, fuentes, fecha y bestArgument. | Explicar reutilización y dependencias con menor reconstrucción. |
| Separación de requisitos y notas | `ui-offer-context/ui-offer-note` implementados; originales conservados. | Granularidad adicional de dependencias, no repetir esta separación como función pendiente. |
| Material y permisos | Revisión, copias inmutables, modos por oferta, autorización y retirada. | Proyección común más explicable; guardias actuales intactas. |
| Trabajo y continuidad | Dueños, instantánea original y send causal elegible; interrupción comprobada y conciliación. | Última frontera visible y detención coordinada; no se garantiza parar el portal. |
| Disponibilidad y candidatura | `ui-availability-check/ui-followup-check`; hechos separados y cronología real. Lograda termina el ciclo. | Integrar esos ejes en la síntesis de decisión sin añadir vigilancia. |
| Interfaz y actividad | Estado común, tabla/ficha/Resumen, historial y documentos enviados. | Misma interpretación para persona y agente; aceptación de claridad separada. |
| Recuperación y entrega | Copia comprobada, carpeta nueva y permisos retirados; edición genérica y procedencia de insumos. | No hay fusión automática ni restauración del estado externo. |

Los límites de la entrega se explican en [limits.md](limits.md) y los cambios en [CHANGELOG.md](../CHANGELOG.md). Los informes de desarrollo permanecen en el proyecto de origen; esta edición no declara nuevas comprobaciones por incorporar el diseño.

La columna existente describe capacidad representada en código y contrato; no declara aceptación humana ni resultados personales. Una propuesta solo pasa a implementada con cambios y comprobaciones correspondientes.

## Orden de evolución

```mermaid
flowchart LR
  D0[D0 Lenguaje y rutas vigentes] --> D2[D2 Situacion suficiente]
  D1[D1 Fronteras y guardias] --> D2
  D2 --> D3[D3 Continuacion derivada]
  D2 --> D4[D4 Reutilizacion explicable]
  D3 --> D5[D5 Aprendizaje medido]
  D4 --> D5
```

D0 se realiza mediante esta consolidación documental. D1 es una condición permanente y tiene prioridad si aparece una ambigüedad de efectos. **El siguiente incremento recomendado es una primera porción de D2**, que incluya la continuidad y las dependencias mínimas de un caso. D3 y D4 se amplían por necesidad demostrada. D5 espera datos suficientes y una pregunta autorizada.

No implementar todas las abstracciones de una vez. Cada incremento atraviesa lectura → decisión → operación existente cuando proceda → relectura → continuación. Una mejora de consulta puede acreditarse sin realizar una transmisión externa.

## D0. Lenguaje común y una fuente por responsabilidad

**Estado:** consolidación de diseño y guía en esta revisión; no cambia el esquema operativo.

**Entrega:** modelo que enlaza identidad, observación, conocimiento, situación, acción, efecto y continuidad; guía aplicable con comandos actuales; mapa de contratos; plan único. La edición genérica recibe el mismo modelo y no datos personales. Los textos previos se preservan como antecedentes fechados.

**Criterios:** cada regla tiene fuente principal y ruta de profundización. Un lector distingue capacidad actual, propuesta y comprobación. Se resuelven en el párrafo vigente las afirmaciones ya sustituidas. Se conservan encabezados y contratos utilizados por la construcción genérica. Coincidir en release.json no demuestra procedencia común de todos los insumos.

**Límite:** mejor organización documental no acredita ahorro medido, aceptación humana, despliegue ni ejecución de la cola.

## D1. Fronteras fiables para poder reutilizar

**Estado:** guardias actuales implementadas; coordinación de detención externa pendiente. El detalle normativo permanece en OPERACION/APLICACION.

Conservar separación entre permiso, material y efecto; dueño e IDs originales; identidad de selección automática; idempotencia del lote exacto; comprobaciones de todos los intentos iniciados aún inciertos; recibo tardío sin reenviar o recuperar permiso; no reencolar cancelled. Una nueva vista nunca relaja estas condiciones.

Conservar distinción entre antigüedad y detención, updatedAt y activityAt, fecha observada y fecha incorporada. Interrupción comprobada e identificador nuevo; ningún mensaje de un dueño invalidado recupera control. Revisión general de 48 horas y comprobación de destino/vacante de hasta 24 horas al usar el paquete, más revalidación inmediata; not_sent conserva su ventana propia.

**Criterios:** dos chats, retirada de permiso, recibo tardío, selección nueva en el mismo segundo, respuesta local perdida e intento incierto conservan propietario, versión y una historia trazable. La lectura selectiva no oculta guardias globales. La detención administrativa no se presenta como parada efectiva del portal.

## D2. Situación suficiente para la siguiente decisión

**Estado:** consulta selectiva básica implementada; contrato uniforme siguiente propuesto. No existe un nuevo comando ni objeto uniforme disponible.

**Primer recorrido:** petición sobre una oferta guardada; orientación del agente; identificación de lo que falta; recuperación de la prueba pertinente; elección del paso admisible; resultado local y punto de continuación. Empezar con datos ficticios y las operaciones existentes. Ampliar a perfil y búsqueda después de demostrar la misma gramática.

| La orientación propuesta debe mostrar | Fundamento y límite |
| --- | --- |
| Ámbito y resultado pendiente | Instalación, oferta/encargo y fase; el mandato llega por canal confiable, no lo inventa la vista. |
| Hechos decisivos y conclusión actual | Fuente, fecha, huella/versión pertinente y referencia recuperable. |
| Dudas que pueden cambiar el paso | Consecuencia y fase; distinguir desconocido, contradicción, desactualizado y dato no incluido. |
| Paso posible o impedimento | Condiciones representadas, motivo y responsable. Una opción no es una selección o autorización. |
| Material, permiso y efecto pertinentes | Referencias al paquete actual y al realmente enviado; efectos inciertos explícitos. |
| Última frontera acreditada | Qué se comprobó, qué sigue incierto y qué condición permite continuar. |
| Alcance omitido | Totales/pendiente donde existan y consulta para ampliar; conservar guardias globales. |

Los rótulos describen el diseño; no son nombres de campos nuevos. La vista debe derivarse de la representación actual. Persistencia adicional requiere demostrar un hecho que no pueda recuperarse correctamente, con su migración prevista.

**Secuencia acotada:**

1. Fijar casos ficticios, respuestas esperadas y línea base del recorrido actual.
2. Derivar una orientación del caso con referencias al detalle. Reutilizar reglas comunes existentes; mantener comandos y rutas compatibles.
3. Recuperar únicamente el fundamento o material que se necesita, declarando ausencia, omisión, pérdida o falta de cálculo. La revisión/transmisión sigue requiriendo material exacto.
4. Comparar con el recorrido completo y comprobar guardias, resultado y continuación.
5. Solo si aporta ahorro adicional, diseñar diferencias del mismo ámbito con los elementos afectados y ruta de relectura. `--since` conserva su contrato actual hasta una implementación separada comprobada.

App y agente deben compartir interpretación de mínimos, versiones, trabajo y efectos, con diferente profundidad. Extraer o reutilizar derivaciones del núcleo existente; no duplicar un motor por interfaz. Conservar la app actual, sus enlaces y pasos de decisión.

**Criterios:** mismos hechos decisivos, restricciones y acciones admisibles que la lectura completa; fuente localizable y omisiones visibles; ningún permiso o cierre deducido. Otra sesión puede retomar sin copiar relatos enteros. Acreditar el coste total, no solo bytes de una respuesta.

## D3. Continuación desde lo realmente comprobado

**Estado:** protocolos existentes; proyección uniforme de continuación pendiente.

**Primer incremento:** derivar de tarea, historia, paquete y comprobaciones la última frontera acreditada, la incierta y el siguiente requisito. Dejar visible qué puede continuar el dueño actual y qué requiere intervención. Forma parte del primer caso de D2.

Añadir una entidad general de intento únicamente si un escenario no puede reconstruirse con precisión desde los registros existentes. La necesidad debe indicar dato perdido, operación que lo produce, propietario, migración y duplicación evitada. Una señal de presencia no transfiere propiedad.

**Criterios:** retomar antes/después de escritura, conservación del paquete y efecto externo; respuesta perdida; chat detenido; copia antigua con cambios posteriores. Continuar sin repetir formulario ni convertir fallo o incertidumbre en done. Una conclusión parcial conserva su prueba y su alcance.

## D4. Reutilización con dependencias comprensibles

**Estado:** respuestas con ámbito, huellas, historia y separación explícita de notas ya existentes. Dependencias uniformes y distinción general entre contenido y observación pendientes.

**Primer incremento:** explicar para una conclusión real qué pregunta resuelve, qué hechos utiliza y qué cambio obliga a revisarla, usando primero los ámbitos de las huellas actuales. Incluirlo en D2 cuando evite reconstrucción.

Separar conceptualmente mismo contenido, aplicabilidad y fecha de comprobación. Afinar una dependencia solo tras demostrar una invalidación innecesaria o una relación oculta. Mantener conservadoras las guardias antiguas durante la migración. Reconfirmar no convierte una observación antigua en consulta nueva ni habilita automáticamente un paquete.

**Criterios:** requisito cambiado afecta al material pertinente; nota independiente no lo invalida; fuente fallida no borra un éxito histórico; respuesta equivalente conserva significado y ámbito; respuesta distinta, consentimiento o permiso no se trasladan. El efecto histórico y su copia permanecen intactos.

**Límite:** ningún grafo por frase, almacén vectorial, memoria paralela o resumen sin fundamento. Las preguntas se declaran con las operaciones actuales y la persona solo responde lo necesario para el paso concreto.

## D5. Aprender a dirigir mejor

**Estado:** pospuesto hasta datos suficientes y pregunta concreta; no es programación.

Separar exactitud operativa, calidad de oportunidades y resultados de empleo. Evaluar una pregunta: dónde se repite lectura, qué incertidumbre genera correcciones o qué información permite elegir/preparar mejor. Recuentos básicos no demuestran causalidad ni probabilidades de contratación.

**Criterios:** una conclusión respaldada cambia una decisión o simplifica el recorrido sin perder exactitud. Declarar muestra, método y límites. El aprendizaje no crea contactos, permisos, variantes experimentales de CV o vigilancia.

## Escenarios de aceptación del sistema

| Escenario | Qué debe mantenerse y poder explicarse |
| --- | --- |
| Agente nuevo, mismo caso | Fundamento localizable, mismas restricciones y continuación válida. |
| Perfil o criterio corregido | Revisión de lo afectado, originales y efectos históricos intactos. |
| Dato pendiente, vacío consciente, cero o false | Significados distintos; pregunta solo cuando haga falta. |
| Duda técnica o condición no publicada | Elección permitida sin inventar aptitud ni cumplimiento. |
| Mínimo explícitamente incompatible | Evidence y decisión del escritor; prioridad no lo compensa. |
| Nueva observación del mismo contenido | Fecha y prueba nuevas si hubo consulta; respetar hoy las invalidaciones existentes. |
| Nota frente a requisito modificado | Dependencias distintas y conservación de Observaciones originales. |
| Otro portal, alias o intermediario | Identidad comprobada o duda; ninguna segunda solicitud por similitud. |
| Cliente final desconocido y exclusión | Duda conservada, sin dar la exclusión por satisfecha ni contactar. |
| Fuente parcial, sesión caducada o salida truncada | Alcance incompleto y paso de recuperación; no afirmar ausencia. |
| Material cambia tras revisión | Nueva revisión/permiso de versión actual, copia enviada intacta. |
| Retirada de permiso y recibo tardío | Impedir efectos futuros y conciliar el intento original sin reenviar. |
| Dueño ajeno o invalidado | No tomar trabajo por silencio ni actualizar con identificador invalidado. |
| Petición nueva durante tanda | Lista original intacta; retirada de permiso respetada. |
| Anuncio cerrado después de enviar | Disponibilidad separada del resultado personal. |
| Rechazo, cierre y oferta del puesto | Procedencia y cronología reales; Lograda final y sin nueva preparación. |
| Recuperar copia antigua | Carpeta nueva, comparación y permisos retirados; no restaurar el portal. |
| Mejora del producto con cola pendiente | Consulta como contexto, sin ejecutar operaciones de empleo. |

Cada recorrido relevante debe comprobar también el retorno: resultado → registro → lectura → continuación. Probar módulos aislados no demuestra por sí solo esa coherencia.

## Medición y evidencia

| Dimensión | Qué registrar |
| --- | --- |
| Exactitud | Hechos y dudas decisivos preservados; restricciones/acciones admisibles; fundamento recuperable; efectos no duplicados. |
| Recursos | Bytes de toda la lectura y salida, número de llamadas, tiempo de proyección/consulta y trabajo repetido al retomar. Tokens solo si se miden con método declarado. |
| Carga humana | Preguntas repetidas, datos ya aportados solicitados otra vez y decisiones comprensibles. Comprensión real requiere personas. |
| Acumulación | Qué resultado anterior se reutiliza, por qué sigue válido y cuánto evita reconstruir. |
| Continuidad | Última frontera encontrada, intervención necesaria y reanudación sin inventar permisos o efectos. |

Comparar los mismos casos y condiciones antes/después, incluyendo ampliaciones y revalidación obligatorias. Declarar si la medición incluye contexto de documentación, cachés y tiempo humano. Mantener separados tiempo observado y estimación. No fijar porcentajes de encaje, ahorro o éxito sin prueba.

La evidencia distingue **diseño**, **implementación**, **comprobación automática**, **comprobación de plataforma**, **aceptación humana/operación real** y **publicación**. Tras cambios de lógica se ejecutan pruebas, migración sin pérdidas, Excel ficticio y comprobaciones de presentación/navegación previstas en OPERACION. Una revisión solo documental necesita enlaces, coherencia de contratos, equivalencia genérica y conservación; no se presenta como nueva validación del producto completo.

## Regla de mantenimiento

Antes de modificar una regla, identifica su fuente principal y qué lecturas, operaciones, vistas, pruebas y documentos genéricos dependen de ella. Actualiza el texto vigente y conserva el antecedente fechado; no añadas una instrucción contradictoria al final.

Una propuesta necesita fricción concreta, entrada/salida, dependencias, alcance mínimo, criterios de aceptación y límites. Si una abstracción no permite decidir mejor, recuperar un fundamento o evitar reconstrucción real, no se incorpora todavía.

Esta revisión consolida D0 y define el siguiente incremento de D2. La síntesis automática, el detalle por referencia, las diferencias pertinentes y las dependencias uniformes siguen pendientes de implementación y evidencia.
