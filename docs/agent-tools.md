# Herramientas recomendadas para tu agente

**Guía vigente · 04/11/2026.** Stubbs Jobs funciona sin estas herramientas, pero con ellas el agente pide menos ayuda y consigue más solicitudes. Este archivo es para el agente que guía a la persona; `agentTools` en `agent-status` indica cuáles faltan.

## Cómo guiar

1. **Una cada vez y sin tecnicismos.** La persona puede usar IA por primera vez: di dónde pulsar, espera su respuesta y comprueba tú el resultado. No pidas varias cosas en un mensaje.
2. **Primero pregunta lo mínimo.** Qué navegador usa y qué correo. Tu propio nombre de agente ya lo conoces.
3. **Explica para qué sirve antes de pedirlo.** Usa `why` y `withoutIt` de `agentTools`.
4. **Comprueba y registra.** Una conexión solo cuenta si la verificaste con tus herramientas. Registra `ui-tool-readiness`:

```json
{"kind": "ui-tool-readiness", "tool": "browser", "status": "connected", "agent": "Claude Code", "proof": "Lo comprobado o las palabras de la persona"}
```

`tool` es `browser` o `mail`. `status` es `connected`, `unavailable` (tu agente o su plan no lo permiten) o `declined` (la persona no lo quiere).

5. **Recomienda sin bloquear.** Si no se puede o no quiere, explica qué cambia y continúa. Al empezar cada tanda, comprueba otra vez las conexiones y recuerda en una frase lo que siga sin conectar.
6. **Las pantallas cambian.** Si lo que ve la persona no coincide, consulta la documentación oficial enlazada; no inventes pasos.

Nunca pidas contraseñas ni inicies sesión por la persona: ella escribe sus credenciales en la página del proveedor. No instales nada que no venga de la tienda oficial o del proveedor.

## Cuándo guiar

- Al terminar la preparación del perfil, antes de la primera búsqueda.
- Cuando la persona pega el mensaje de la app o pide conectar sus herramientas.
- Antes de una tanda, si `pending` no está vacío.

## Extensión del navegador

Usa las sesiones que la persona ya tiene abiertas y permite adjuntar archivos. Después de instalarla, debe iniciar sesión en ese navegador en los portales que use.

### Con Claude

Funciona con Google Chrome y Microsoft Edge ([documentación](https://code.claude.com/docs/en/chrome)). Requiere un plan directo de pago de Claude; si el plan no lo permite, registra `unavailable`.

1. Abre en el navegador la [página de la extensión](https://chromewebstore.google.com/detail/claude/fcoeoabgfenejglbffodgkkbkcdhcgfn).
2. En Edge, si aparece el aviso, pulsa **Permitir extensiones de otras tiendas**.
3. Pulsa **Añadir** y confirma.
4. Abre la extensión e inicia sesión con la misma cuenta y organización que usa el agente.
5. Cierra el navegador por completo, vuelve a abrirlo y empieza una sesión nueva del agente.

**Comprobación:** `list_connected_browsers` debe devolver el navegador. Si no aparece, comprueba que está activada en `edge://extensions` o `chrome://extensions` y reinicia navegador y agente.

### Con ChatGPT o Codex

Funciona con Chrome, Edge, Brave, Opera y Vivaldi ([documentación](https://learn.chatgpt.com/docs/chrome-extension)).

1. Actualiza la app de escritorio de ChatGPT.
2. Abre **Settings > Computer Use**. Si no ves tu navegador, despliega **More browsers**.
3. Pulsa **Install** junto al navegador e instala la extensión desde su tienda.
4. Vuelve a **Computer Use** y comprueba que aparece **Manage**.
5. En un chat, elige el navegador con una mención `@`, usando el perfil donde instalaste la extensión.
6. Para adjuntar archivos, abre los detalles de la extensión y activa **Allow access to file URLs**.

La documentación oficial describe el paso 6 solo para Chrome: pruébalo en otro navegador antes de contar con él. **Comprobación:** abre una pestaña y lee su título.

### Sin cuenta en un portal

No hace falta para empezar: el agente busca donde el portal lo permite y salta al siguiente. Si una oferta que encaja exige cuenta, se lo dice a la persona con el portal y qué necesita; solo ella la crea y escribe su contraseña. Cuando compruebe una sesión, registra `ui-portal-access` para que Mi perfil lo muestre. Algunos portales limitan el uso automático de la cuenta: respeta sus avisos.

### Sin extensión

Si el agente tiene navegador integrado, la persona inicia sesión ahí en sus portales. Los formularios que exigen subir un archivo pueden no admitir un CV adaptado: en ese caso se usa el CV guardado en el portal, indicándolo en el informe.

## Conector de correo

Sirve para dos cosas muy concretas, con el permiso `applicationVerification` guardado: completar la verificación que pide un portal y localizar el acuse de una solicitud sin recibo. **No sirve para buscar ofertas ni para revisar el resto del buzón.** Conectar el correo no concede ese permiso: pregúntalo aparte, con estas palabras, y guarda su respuesta con `ui-email-verification-settings`.

### Con Claude

Está en todos los planes ([documentación](https://support.claude.com/en/articles/15183774-connect-to-microsoft-365)).

1. En Claude, abre **Customize > Connectors**.
2. Busca **Microsoft 365** y pulsa **Connect**.
3. Elige cuenta personal o de trabajo, según el correo. Las cuentas personales (Outlook.com, Hotmail, Live, MSN) están en los planes Free, Pro, Max y Ultra. En una organización puede hacer falta un administrador.
4. Inicia sesión en la página de Microsoft y acepta los permisos.

**Comprobación:** busca un mensaje con una consulta acotada y sin mostrar su contenido; empieza una sesión nueva si las herramientas no aparecen.

### Con ChatGPT o Codex

OpenAI ofrece [Outlook Email](https://help.openai.com/en/articles/12512241-outlook-email-and-calendar-apps-in-chatgpt) como app conectada. Búscala en los ajustes de apps o conectores de ChatGPT y sigue su guía; no se ha comprobado que un chat de Codex pueda usarla. Si tu sesión no ve el correo, registra `unavailable`.

### Otro correo o sin conector

Si usa otro correo, conecta el equivalente solo si tu agente lo ofrece oficialmente. Si no, registra `unavailable`: la persona confirma esos correos y pulsa **Ya he completado el acceso** en la oferta.
