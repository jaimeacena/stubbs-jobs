# Auto-solicitud sin interrupciones

**Guía vigente · 21/10/2026.** Procedimiento estándar para presentar las solicitudes de las ofertas que la persona eligió en **Auto-solicitud**. No amplía permisos: aplica los que la persona ya guardó. Las guardias del escritor, [operations.md](operations.md) y [application-contract.md](application-contract.md) siguen vigentes; esta guía ordena cómo cumplirlas sin detenerse en cada paso.

## Principios

1. **El permiso ya está dado.** Elegir una oferta en Auto-solicitud autoriza su envío tras `ui-review`. Los permisos de `autoApply` en `agent-status` (Mi perfil › Sobre mi › «Permisos para Auto-solicitud») cubren los pasos habituales del portal. Con `true`, actúa sin volver a preguntar. Con `false` o `null`, ese paso no está autorizado: bloquea solo esa oferta.
2. **Una oferta bloqueada nunca detiene la tanda.** Registra `blocked` con `summary`, `need` y `proof` y continúa con la siguiente.
3. **No preguntes a mitad de la tanda.** Reúne preguntas, accesos y decisiones pendientes y preséntalos juntos al final.
4. **Nunca inventes.** Ni respuestas, ni experiencia, ni cifras, ni conversiones que la persona no haya autorizado.

## 1. Al empezar (una sola vez)

1. `agent-status --execution-id ID_PROPIO`: lee `autoApply`, `queuedSnapshot`, `eligibleContinuations` y las ofertas con `selection.mode = auto`. Fija la tanda con `--request-ids`.
2. Comprueba qué portales usa cada oferta y si hay sesión abierta (`portalAccess`). Si la persona tiene que iniciar sesión en alguno, díselo ahora en **un solo mensaje** con todos los portales y sigue con las ofertas que no lo necesitan.
3. Si tu herramienta o tu navegador exigen una confirmación humana para enviar formularios o aceptar condiciones, pídela **una sola vez para toda la tanda**: lista de ofertas (empresa · puesto · portal) y los permisos de `autoApply` que vas a aplicar. Una respuesta afirmativa cubre esa tanda; no vuelvas a pedirla por oferta ni por paso.

## 2. Preparar cada oferta (review)

Usa `prepare` (docs/operations.md, «Preparar y enviar una oferta en tres comandos»): una sola descripción JSON registra hechos del anuncio, evidencias, valoración, encaje, CV, formulario, respuestas y revisión; el comando calcula huellas y valores esperados.

- Abre el formulario real y recórrelo **hasta la página del botón final sin pulsarlo**. Declara todas sus preguntas en `ui-draft` (`questions`, `requiredAnswers`, `formAnswerKeys`, `messageUsage`). Las preguntas que aparecen por primera vez al enviar son la causa más frecuente de paradas.
- Responde con los datos confirmados de Mi perfil. Con `autoApplyDerivedAnswers = true`, responde también lo que se deduce sin ambigüedad (años calculados con las fechas de la experiencia, Sí o No según lo que figura en ella, equivalencias estándar de nivel de idioma) y anota la deducción en `proof`.
- Una pregunta sin respuesta posible: decláralo con `scope: global` si sirve para otras candidaturas (la persona la responde una vez en Mi perfil y se reutiliza) y bloquea solo esa oferta con `need: answers`.
- Prepara el CV (`build-cv` o `reused` con motivo), registra `ui-review` y continúa con el `send` de `eligibleContinuations` en la misma tanda.

## 3. Enviar: qué hacer en el portal sin preguntar

`send-start --case ID` inicia el envío y te da el CV listo para adjuntar con su nombre, las respuestas y la presentación. Rellena el formulario con ese material y registra el resultado con `send-finish`: `sent` con la confirmación del portal, o `not_sent` / `unknown` con `need`, `summary` y las preguntas nuevas en `form`; el comando deja la comprobación del portal registrada.

| Situación | Acción |
| --- | --- |
| Aviso de cookies | Rechazar las no necesarias. Siempre. |
| Aviso de privacidad o tratamiento de datos para esta selección | Aceptar si `autoApplyPrivacy` es true. Plazos y destinos de conservación: usar los permisos de «Permisos sobre mi CV y contacto». Si la cláusula excede lo autorizado, bloquear la oferta. |
| Condiciones de uso necesarias para presentar la solicitud | Aceptar si `autoApplyTerms` es true y no implican pagos, suscripciones ni cesión para otros fines. Si no, bloquear la oferta (`need: decision`). |
| Boletines, marketing, alertas, contacto comercial | Rechazar. Siempre. |
| Bolsa de talento opcional | Según `autoApplyTalentPool`; sin permiso, no unirse. |
| Encuesta demográfica opcional | Según `demographicSurveyParticipation`. |
| Pregunta con respuesta guardada o deducible autorizada | Responder y continuar. |
| Pregunta obligatoria sin respuesta | No inventar. `blocked`, `need: answers`, pregunta declarada; siguiente oferta. |
| Sesión del portal ya abierta | Usarla si `autoApplySessions` es true. |
| Hace falta iniciar sesión, crear cuenta, contraseña o código | No crear cuentas ni escribir contraseñas. `blocked`, `need: access`, paso exacto para la persona. |
| CAPTCHA, hCaptcha, Cloudflare, aviso antibots | No resolver ni sortear. `blocked`, `need: access`. La persona puede completarlo y pulsar «Ya he completado el acceso», o enviarla y pulsar «Ya la he enviado yo». |
| Aviso de automatización o restricción de cuenta | Dejar de usar ese portal en esta tanda: bloquear sus ofertas y seguir con las demás. |
| Vídeo, prueba técnica o declaración personal | `blocked`, `need: decision`. |
| Error del portal o adjunto que no carga | Un solo reintento razonable; después `blocked`, `need: other`, con captura o texto. |
| Botón final | Con `autoApplySubmit` true, pulsarlo sin pedir confirmación. Registrar `sent` solo con confirmación real del portal. |

Si te detienes **antes** de pulsar el botón final, dilo en `proof` y registra a continuación `ui-delivery-check` con `outcome: not_sent`. Esa constancia vale una hora: cuando la oferta se desbloquee (respuestas guardadas, acceso completado), vuelve a mirar el portal tú mismo y registra otra comprobación `not_sent` justo antes de revisar o enviar de nuevo; no hace falta la persona. Si pulsaste el botón y no hay recibo, es `unknown` hasta comprobarlo; nunca repitas el formulario sin comprobar.

## 4. Al terminar: un único resumen

Envía a la persona un solo mensaje con:

- **Enviadas** con su confirmación.
- **Preguntas pendientes**, agrupadas y sin repetir. Se responden en la app (Mi perfil o la ficha de la oferta); al guardarlas, la oferta vuelve sola a la cola.
- **Accesos o verificaciones** que debe completar, con el portal y el paso exacto.
- **Decisiones** que solo ella puede tomar.

Después, «Continúa con Stubbs Jobs» retoma lo desbloqueado.

## Límites que Stubbs Jobs no puede quitar

- Los CAPTCHA y verificaciones antibots están para impedir automatizaciones: el agente nunca los resuelve.
- Las contraseñas y la creación de cuentas son de la persona.
- Las normas de seguridad de cada agente o navegador están por encima de esta guía. Si un agente exige confirmar cada envío, la confirmación única del apartado 1 es la forma de reducirlo al mínimo; si aun así insiste, respétalo y deja constancia una vez.
- Muchos portales prohíben la automatización y pueden restringir la cuenta. Elegir Auto-solicitud acepta ese riesgo para esas ofertas.
