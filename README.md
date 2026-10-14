<p align="center"><img src="https://raw.githubusercontent.com/jaimeacena/stubbs-jobs/main/app/assets/stubbs.png" width="112" alt="Stubbs, an orange cat wearing a tie"></p>

# Stubbs Jobs

[Español](README.es.md)

**Your job search, organized and under your control.**

Stubbs Jobs is a Windows app that brings together your profile, job opportunities, résumés and applications. It works with an AI agent in its own chat: the agent discovers opportunities and prepares applications; you choose the jobs and the authorization mode for each one.

**Version 1.0.0 · Windows x64 · Spanish interface**

## Download and get started

1. [Download Stubbs Jobs for Windows](https://github.com/jaimeacena/stubbs-jobs/releases/download/v1.0.0/Stubbs-Jobs-1.0.0-Windows-x64.zip).
2. Right-click the ZIP → **Properties** → tick **Unblock** if it appears. Extract the **entire ZIP** into a local folder that OneDrive, Dropbox or Google Drive do not sync (for example `C:\StubbsJobs`) and open **Abrir Stubbs Jobs.exe**. Python and the required libraries are included.
   The launcher is not digitally signed yet. If Windows shows «Windows protected your PC», choose **More info → Run anyway**. You can first compare the ZIP with `SHA256SUMS.txt` from the same release.
3. Open an AI agent that can work with files on your computer (see [What you need](#what-you-need)). Add that folder as a project, paste the message shown by the app into a new chat and answer its questions. You can attach your CV or start without one.
4. When you want to start searching, ask the agent **«Busca ofertas nuevas»**.

## What you need

- Windows 10 or 11, 64-bit.
- An AI agent that can read and write files and run commands in a folder on your computer. Web chats such as chatgpt.com or claude.ai cannot do this. For example:
  - **Claude Code**, in the Code tab of the [Claude desktop app](https://claude.com/download). It needs a paid Claude plan.
  - **Codex** by OpenAI ([chatgpt.com/codex](https://chatgpt.com/codex)). It needs a ChatGPT plan that includes Codex.
- To search and apply, the agent also needs browser access. Portals that require an account ask you to sign in yourself; the agent never asks for your passwords.

The download does not include accounts, subscriptions or access to job portals; costs and terms belong to the service you choose. Each new chat reads Stubbs Jobs' instructions first, which uses part of your plan. The app opens Edge when available, or your default browser.

## What you can do

- **Mi perfil:** maintain your experience, search criteria and résumé library, with multiple search profiles.
- **Ofertas:** compare opportunities, filter the table and inspect each application. **Solicitar con revisión** requires your approval of the final package. **Auto-solicitud** permits submission for that selected opportunity after the agent's checks.
- **Resumen:** view historical counts and activity grouped by day, with direct links to opportunities and requests that need your attention.

Saving a profile or copying a request does not start a search or submit an application. Continue pending work from the agent's chat with **«Continúa con Stubbs Jobs»**. Selecting, preparing and authorizing an application are separate from confirmed delivery.

## Job portals and their terms

The agent searches and applies with your browser and your accounts. Many portals, such as LinkedIn, Indeed or InfoJobs, forbid automated use in their terms: automated searching or applying may get your account limited or closed. If you do not want that risk, use **Solicitar con revisión** and submit the final application yourself, check each portal's terms and do not ask the agent for more activity than you would do yourself. You are responsible for the use of your accounts.

## Data and boundaries

The download starts empty. Your information is stored in your folder; your chosen agent may read and process it according to its provider's terms. Use **Copias de seguridad** to keep verified backups, and share the original empty ZIP.

There is no automatic updater or synchronization between computers. Automated checks use fictional data and do not demonstrate real submissions, acceptance on another computer or human accessibility review. See the [validation limits](docs/limits.md).

## Documentation and development

- [Documentation index](docs/README.md)
- [User guide in Spanish](docs/user-guide.md)
- [Development and verification](docs/development.md) · [Español](docs/development.es.md)
- [System design](docs/system-design.md) and [agent workflow](docs/agent-guide.md)
- [Backup and recovery](docs/backup-and-recovery.md)
- [Release notes](CHANGELOG.md)
- [How to contribute](https://github.com/jaimeacena/stubbs-jobs/blob/main/CONTRIBUTING.md) · [Security policy](https://github.com/jaimeacena/stubbs-jobs/blob/main/SECURITY.md)

Public source packages contain generic code and fictional tests. Keep personal profiles, résumés, application packages and backups separate from public source.

## Authorship and license

Created by [jaimeacena](https://github.com/jaimeacena). Implementation, verification and the logo were developed with AI assistance; this is disclosed in the [authorship notes](docs/authorship.md).

Licensed under [MIT](LICENSE). Included components and notices are listed in [third-party notices](docs/third-party-notices.md).
