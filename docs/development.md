# Developing Stubbs Jobs

[Español](development.es.md) · [Documentation index](README.md)

Version 1.0.1 · 2026-10-21. The ready-to-use Windows download is available on [GitHub Releases](https://github.com/jaimeacena/stubbs-jobs/releases). Read [AGENTS.md](../AGENTS.md) before changing the product. Commands below run from the project root.

## Set up a development copy

Windows x64 is required. You can copy only `runtime/python` from this release's ZIP into the source folder and build the launcher:

```powershell
.\tools\build-launcher.ps1
```

Open `Abrir Stubbs Jobs.exe`. A new installation starts with an empty profile. Keep development and personal installations separate; only `tools/stubbs_jobs.py` may write the operational registry.

Alternatively, use your own Python environment for development:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B tools/stubbs_jobs_app.py --open
```

This environment does not replace the embedded Python required by the Windows distribution builder. [Third-party notices](third-party-notices.md) identify the distributed runtime and libraries.

## Verify changes

Install Node.js 24 for interface tests. Build the Windows launcher first, then run the quality check with your prepared Python:

```powershell
& ".\runtime\python\python.exe" -B tools/check-quality.py --output outputs/new-check
```

If you use a virtual environment, substitute its Python executable. Use a new output folder to preserve previous results. The check covers Python syntax and tests, JavaScript syntax, presentation and interface flows using fictional data. GitHub runs the same entry point on Windows for pushes and pull requests.

XLSX tests also require `@oai/artifact-tool`, which is not redistributed. If it is unavailable, tests report their omission; CSV remains available. The optional native Edge icon check requires `STUBBS_JOBS_NATIVE_ICON_TEST=1` and creates and closes only its own fictional window. Automated checks do not establish human acceptance or actual delivery; see [validation limits](limits.md).

## Build an empty distribution

Use the verified embedded Python 3.14.7 runtime for Windows x64. Build the launcher with the current icon before packaging:

```powershell
.\tools\build-launcher.ps1
& ".\runtime\python\python.exe" -B tools/build-share.py outputs/Stubbs-Jobs-1.0.1-Windows-x64 --runtime runtime/python
& ".\runtime\python\python.exe" -B tools/build-source.py outputs/Stubbs-Jobs-1.0.1-Windows-x64 outputs/Stubbs-Jobs-1.0.1-Source
```

The builders use explicit allowlists, verify release identity, license and provenance, and produce SHA-256 manifests. They reject existing destinations and mixed source revisions. Public source is prepared from the verified empty distribution; it does not copy a personal installation's Git history or operational data.

## Documentation layout

`README.md` and `README.es.md` present the project. `docs/` contains guides, contracts and design documents with English filenames; the operating contracts remain in Spanish. `AGENTS.md` and `CLAUDE.md` remain at the root as agent entry points.

`distribution/` contains reviewed generic templates used by both builders. Update their matching documentation when a shared rule changes. The local `private/` folder is excluded from Git and is never a packaging input; the builder creates a blank `private/profile.md` from its reviewed template. Older root-level personal documents remain readable and recoverable for compatibility.

Share only the empty ZIP. Do not publish `data`, `outputs`, `private`, personal résumés, packages, credentials or backups. [Backup and recovery](backup-and-recovery.md) explains how to update a used installation without overwriting it.
