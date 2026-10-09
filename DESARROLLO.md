# Desarrollo de Stubbs Jobs

Edición 1.0.0 · 2026-10-09. La descarga para usar la app está en [GitHub Releases](https://github.com/jaimeacena/stubbs-jobs/releases). Trabaja en una copia del [repositorio de código](https://github.com/jaimeacena/stubbs-jobs) y lee [AGENTS.md](AGENTS.md) antes de modificar el producto.

## Preparar el código

Se necesita Windows de 64 bits. Puedes copiar únicamente `runtime/python` desde el ZIP de esta versión a esta carpeta y compilar el acceso:

```powershell
.\tools\build-launcher.ps1
```

Después abre `Abrir Stubbs Jobs.exe`. Empezará con un perfil vacío. Conserva separados desarrollo y datos personales; únicamente `tools/stubbs_jobs.py` puede escribir el registro operativo.

También puedes usar un entorno de Python propio para desarrollar:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B tools/stubbs_jobs_app.py --open
```

Este entorno no sustituye al Python embebido exigido por el constructor de la descarga. [TERCEROS.md](TERCEROS.md) identifica el runtime distribuido y sus bibliotecas.

## Comprobar cambios

Instala Node.js 24 para las pruebas de interfaz. Compila primero el acceso de Windows y ejecuta con el Python preparado:

```powershell
& ".\runtime\python\python.exe" -B tools/check-quality.py --output outputs/comprobacion-nueva
```

Si elegiste un entorno propio, utiliza su ejecutable de Python en lugar del de `runtime/python`. El destino debe ser nuevo. Se comprueban sintaxis, pruebas de Python, presentación y recorridos de interfaz con datos ficticios. Los resultados se conservan en esa carpeta. GitHub ejecuta el mismo control en Windows para los cambios y propuestas.

Las pruebas de XLSX requieren además `@oai/artifact-tool`, que no se redistribuye. Si falta, se omiten con su motivo; CSV permanece disponible. La comprobación nativa aislada de Edge requiere `STUBBS_JOBS_NATIVE_ICON_TEST=1` y crea y cierra únicamente su propia ventana ficticia. Las pruebas automáticas no acreditan un envío real ni aceptación humana: consulta [LIMITES.md](LIMITES.md).

## Construir una descarga vacía

Usa el runtime de la descarga, que contiene Python embebido 3.14.7 para Windows x64. Compila el acceso con el icono actual antes de construir:

```powershell
.\tools\build-launcher.ps1
& ".\runtime\python\python.exe" -B tools/build-share.py outputs/Stubbs-Jobs-1.0.0-Windows-x64 --runtime runtime/python
& ".\runtime\python\python.exe" -B tools/build-source.py outputs/Stubbs-Jobs-1.0.0-Windows-x64 outputs/Stubbs-Jobs-1.0.0-Codigo
```

Los constructores utilizan listas explícitas, verifican versión, licencia y procedencia y generan manifiestos SHA-256. Rechazan destinos existentes y mezclas de revisiones. El código público se prepara desde la descarga verificada; no copia el historial ni los datos de una instalación personal.

Comparte únicamente el ZIP vacío. No publiques `data`, `outputs`, perfiles personales, CV, paquetes, credenciales ni copias de seguridad. [RECUPERACION.md](RECUPERACION.md) explica cómo actualizar una instalación usada sin sobrescribirla.
