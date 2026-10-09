$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
$compilerPath = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$iconPath = Join-Path $projectPath 'app\assets\stubbs.ico'
if (-not (Test-Path -LiteralPath $compilerPath)) { throw 'No se encuentra el compilador de Windows.' }
if (-not (Test-Path -LiteralPath $iconPath -PathType Leaf)) { throw 'Falta el icono de Stubbs Jobs en app\assets\stubbs.ico.' }
& $compilerPath /nologo /target:winexe /reference:System.Windows.Forms.dll ('/win32icon:' + $iconPath) ('/out:' + (Join-Path $projectPath 'Abrir Stubbs Jobs.exe')) (Join-Path $PSScriptRoot 'launcher.cs')
if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el acceso de Stubbs Jobs.' }
