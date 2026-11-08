# Changelog

All published versions of Panel DDEV. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[SemVer](https://semver.org/).

## [0.4.0] - 2026-11-07

### Added
- **Clone from your GitHub repositories**: "My repositories…" in the clone
  dialog lists your repositories and those of your organizations (via the
  GitHub CLI), with search, private/fork/archived tags, language and last
  update. Picking one fills the URL using your gh git protocol (HTTPS or SSH).

## [0.3.0] - 2026-11-07

### Added
- **Tray icon**: open sites, start, stop and restart projects, stop all, and
  "Open at login" (starts hidden in the tray). Closing the window keeps the app
  running in the tray; "Quit" exits.
- **Preferences** (menu ☰): interface language **English or Spanish** (or the
  system language) and **light, dark or system** theme. The embedded terminal
  follows the theme.
- `README.es.md` and `TERMS.md` (English terms; Spanish in `TERMINOS.md`).

### Changed
- Source code, comments and the default UI language are now English; Spanish
  is provided as a translation.
- The installer is now `install.sh` (was `instalar.sh`) and speaks the system
  language.
- The header bar "About" button moved into a menu with Preferences and Quit.

## [0.2.0] - 2026-11-07

### Added
- **Git** tab per project: changes with checkboxes to stage them, coloured
  diffs, commit history, commit (Ctrl+Enter), switch and create branches,
  fetch, pull and push. Projects without git can be initialized.
- `.deb` package and installer that sets up Docker, DDEV, mkcert and the app.
- **About** window with version, license and terms.
- MIT license and terms of use.

## [0.1.0] - 2026-11-07

### Added
- DDEV project list with status; start, stop, restart and stop all.
- New projects (PHP, Laravel, WordPress, Symfony, Drupal…) choosing PHP, Node,
  Apache/nginx and database.
- Clone repositories with git, configure and install dependencies.
- Change a project's settings (including MariaDB ↔ MySQL migration).
- Tools: container shell, logs, phpMyAdmin, Mailpit, database import/export,
  composer and npm install.
- Embedded terminal showing every action.
