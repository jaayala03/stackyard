# Changelog

All published versions of Panel DDEV. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[SemVer](https://semver.org/).

## [0.10.0] - 2026-11-07

### Added
- **Share** (Tools → Share…): creates a temporary public link to your site with
  `ddev share`, using Cloudflare quick tunnels (free, no account) or ngrok if
  that is what you have. When the link is ready a window shows it with "Copy
  link" and "Open"; closing the share tab stops sharing. If cloudflared is
  missing, the app offers to install it from Cloudflare's official repository.

## [0.9.0] - 2026-11-07

### Added
- **.env editor** (Tools → Edit .env…): edit `.env` and the other `.env.*`
  files of the project with key and comment highlighting. Creates `.env` from
  `.env.example` with one click, keeps the previous version as `.env.bak`,
  saves with Ctrl+S and, for Laravel, can clear the config cache afterwards.

## [0.8.0] - 2026-11-07

### Added
- **Xdebug switch** in the project configuration: shows whether Xdebug is on
  and toggles it (`ddev xdebug on/off`). It stays on until the project restarts.

## [0.7.0] - 2026-11-07

### Added
- **Database snapshots** (Tools → Snapshots…): create named snapshots of the
  project database, see their date, size and database version, restore one
  (with confirmation) or delete it. Uses `ddev snapshot`.

## [0.6.0] - 2026-11-07

### Added
- **Quick commands** on the project page:
  - Framework shortcuts: Laravel (migrate, migrate:fresh --seed with
    confirmation, optimize:clear, test, tinker, queue:work), WordPress (wp-cli
    updates, cache flush, users), Symfony, Drupal (drush), Craft CMS,
    CodeIgniter, CakePHP and Magento.
  - The scripts of the project's `package.json` (`npm run dev`, `build`…);
    watchers like `dev` open as interactive terminals.
  - `composer update` when the project has a `composer.json`.
  - **Your own commands**, saved per project ("Add command…"); right-click one
    to remove it.

### Fixed
- Changing preferences no longer overwrites other saved settings.

## [0.5.0] - 2026-11-07

### Added
- **Add folder**: use a folder you already have with DDEV. The project type and
  public folder are detected (Laravel, WordPress, Drupal, Symfony, CodeIgniter,
  Craft CMS, CakePHP, Magento or plain PHP); if the folder already has a
  `.ddev/config.yaml`, its values are loaded. Optionally installs dependencies.
- Automated smoke tests for the generated scripts (`packaging/test_scripts.py`),
  run on every package build.

### Fixed
- Project actions (start, stop, create, clone…) failed immediately in 0.3.0
  and 0.4.0 because of a quoting error in the generated scripts. Please update.

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
