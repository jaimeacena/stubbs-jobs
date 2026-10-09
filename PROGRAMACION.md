# Programación opcional

La búsqueda funciona mediante una petición al agente. Programarla requiere una instrucción expresa con carpeta real, frecuencia, zona horaria, alcance y avisos deseados. Stubbs Jobs no activa ni verifica ese horario y no promete trabajo con el equipo apagado. Sin esa instrucción no se crea programación.

La tarea programada es otra entrada al protocolo de OPERACION.md, no otro motor. Comparte perfil, cola, propietarios, revisiones y permisos con el trabajo manual. No usar una copia del código sin los datos de esa persona ni iniciar agent_runner.py como lanzador local.

## Alcance y secuencia

1. Comprobar carpeta, mandato guardado y perfil mediante agent-status, consulta sin escritura. Ampliar por caso/encargo/perfil cuando corresponda. status/app-status conservan sus usos de compatibilidad. Si falta perfil, pedir el paso de INICIO.md y terminar. Con otro trabajo starting/running, no planificar ni tomarlo.
2. Solo si esta programación autoriza búsqueda, ejecutar plan. Puede planificar descubrimiento y preparaciones de ofertas ya seleccionadas; una prioridad A no equivale a elección. No crea permisos nuevos, duplica pendientes ni desbloquea fallos automáticamente.
3. Obtener queuedSnapshot o handoff; releer cada ID antes de marcar su inicio. Usar execution-id propio y la misma lista original --request-ids en todos los apply: queda inmutable al primer inicio. eligibleContinuations solo permite el envío derivado de una preparación automática original propia ya terminada, con oferta/selección/paquete/permiso vigentes. Los otros cambios quedan para nueva instantánea; toda retirada de permiso se respeta antes de efectos futuros.
4. Para transmitir, cumplir paquete/permiso exactos y comprobar todos los intentos iniciados aún inciertos de esa oferta. not_sent fresco se consume al iniciar realmente el nuevo intento; una tarea cancelled no se reencola. No reintentar automáticamente. La excepción de applicationVerification solo permite el enlace requerido por una solicitud autorizada ya presentada en la cuenta guardada; no permite leer otros mensajes ni captar empleo por correo.
5. Releer el resultado y conservar cobertura, incidencias, prueba y siguiente paso. Avisar según la instrucción: cambios relevantes, fallo o decisión necesaria. Si nada cambió ni exige intervención, permanecer en silencio salvo que se hayan pedido informes periódicos.

Una programación no autoriza otras ofertas, contactos, experimentos, exportaciones o publicación. Si sus condiciones cambian, se modifica solo por petición. Modificar estas instrucciones no cambia automáticamente tareas ya configuradas en un proveedor; actualizarlas allí dentro del alcance pedido.

## Petición de ejemplo

> Programa una búsqueda de Stubbs Jobs en la carpeta que te indique, con la frecuencia y zona horaria que confirme. Sigue AGENTS.md y la entrada común de OPERACION.md, utiliza mi perfil actual y prepara solicitudes solo para ofertas que haya seleccionado. Respeta los permisos concretos y las ejecuciones existentes. Avísame de resultados relevantes, fallos o decisiones necesarias.

El ejemplo necesita los datos e instrucción reales antes de crear una tarea. La programación y el agente no acreditan por sí mismos que una búsqueda o un envío se hayan ejecutado.
