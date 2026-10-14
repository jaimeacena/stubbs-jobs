# Contributing to Stubbs Jobs

[Español más abajo](#contribuir-a-stubbs-jobs)

Thank you for helping. Stubbs Jobs is a Windows app with a local Python service, a plain JavaScript interface and an AI agent protocol. Bug reports, tests with fictional data and documentation fixes are especially welcome.

## Before you start

- **Never include personal data** in issues, pull requests or tests: no real CVs, names, emails, phone numbers, registries (`data/registry.json`) or application packages. Use fictional values such as `persona.ficticia@example.org`.
- Discuss large changes in an issue first. The agent rules in `AGENTS.md` and `docs/` are a contract: a change to one rule must update its dependent documents and tests.

## Development

1. Install Python 3.14 and Node 24 on Windows (CI uses `windows-latest`).
2. `python -m pip install -r requirements.txt`
3. Build the launcher: `powershell -File tools/build-launcher.ps1`
4. Run every check: `python -B tools/check-quality.py --output outputs/check-1` (use a new folder each time).

See [docs/development.md](docs/development.md) for packaging and the empty Windows download.

## How changes are published

This public repository is generated from the maintainer's source tree by `tools/build-source.py`, which verifies provenance and rejects personal data. Pull requests are reviewed here; accepted changes are applied to that source tree and published in the next release with credit in `CHANGELOG.md`. Your pull request may therefore be closed after being merged upstream rather than merged directly.

---

# Contribuir a Stubbs Jobs

Gracias por ayudar. Son especialmente útiles los informes de errores, las pruebas con datos ficticios y las correcciones de documentación.

- **No incluyas nunca datos personales** en incidencias, solicitudes de cambio o pruebas: ni CV, nombres, emails, teléfonos, registros (`data/registry.json`) ni paquetes de candidatura reales. Usa valores ficticios.
- Comenta antes en una incidencia los cambios grandes. Las reglas del agente en `AGENTS.md` y `docs/` son un contrato: cambiar una regla exige actualizar sus documentos y pruebas dependientes.
- Para desarrollar: Python 3.14 y Node 24 en Windows, `python -m pip install -r requirements.txt`, `powershell -File tools/build-launcher.ps1` y `python -B tools/check-quality.py --output outputs/comprobacion-1` (carpeta nueva cada vez). Detalles en [docs/development.es.md](docs/development.es.md).
- Este repositorio se genera desde el código del mantenedor con `tools/build-source.py`, que comprueba la procedencia y rechaza datos personales. Las aportaciones aceptadas se aplican allí y se publican en la siguiente versión, con crédito en `CHANGELOG.md`; por eso una solicitud de cambio puede cerrarse tras incorporarse en lugar de fusionarse directamente.
