# Changelog

All published versions of Stackyard (called Panel DDEV before 1.1.0). The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[SemVer](https://semver.org/).

## [1.5.0] - 2026-11-08

### Added
- **Deploy** tab for projects with a pm2 ecosystem file
  (`ecosystem.config.js`, `.cjs`, `.mjs`, `.ts`, `.json`, `.json5`, `.yaml`,
  `.yml`, `ecosystem.*`, `pm2.config.*`, `process.json`…):
  - environment selector (production, staging…) with server, folder, branch,
    repository and post-deploy command;
  - **Deploy** (`pm2 deploy`), **Roll back** (`revert 1`), **First-time setup**,
    **Reload app**, **Status** (`pm2 ls`), **Live logs** and **Test connection**
    on the server, with confirmation for the actions that change production;
  - **Load my SSH keys** (`ddev auth ssh`); everything runs in the project's
    container, so Node and pm2 are not needed on this computer.
- Local Node services follow the ecosystem: the service that runs an app's
  script takes its pm2 name and port, and the other apps (workers, cron
  scripts…) run as background services.
- JS/MJS/CJS/TS ecosystem files are read with the Node of the DDEV image, in a
  container without network; secrets in `env*` blocks are never shown.

## [1.4.0] - 2026-11-08

### Added
- **Node.js projects**: Express, Fastify, Koa, NestJS… backends and Vite
  frontends, including monorepos with `backend/` and `frontend/` folders, are
  detected when you clone or add them (or choose the new "Node.js" type), and
  set up without Node on your computer:
  - every part runs as a DDEV service with its own URL (the frontend on the main
    URL, the backend on its own port), without a PHP web server or database
    unless the code uses MySQL/MariaDB or PostgreSQL;
  - dependencies are installed inside the container on start; native modules
    (bcrypt, sqlite3, sharp…) are rebuilt for Linux when `node_modules` came
    from another system, and checked one by one because npm 11 skips install
    scripts that are not allowed explicitly;
  - `.env` files are created from `.env.example` with the DDEV URLs, secrets such
    as `JWT_SECRET` are generated, and the keys that need a real value (API
    keys, tokens) are listed;
  - Vite runs through a wrapper config that allows the local domain and makes
    hot reload work, without touching the project's `vite.config`;
  - Chromium is installed for Puppeteer when the project uses it;
  - Tools → "Set up for Node…" applies or refreshes all of this on an existing
    project; "npm install" installs every service.
- **HTTP or HTTPS** per project (new, clone, add folder and settings): used for
  the URL the app shows and opens and, in Node projects, for the `.env` URLs and
  Vite's hot reload.
- The **.env editor** finds `.env` files in sub-folders (e.g. `backend/.env`,
  `frontend/.env.development`) and creates any of them from its example file.

### Changed
- Node projects hide the PHP-only tools (Xdebug, Composer) and the database
  tools when there is no database.

### Fixed
- `.env` files that start with a UTF-8 BOM (saved by some Windows editors) are
  read correctly.

## [1.3.1] - 2026-11-08

### Fixed
- The New / Clone / Add folder dialogs were taller than small screens (e.g.
  1280×800 with a taskbar), hiding the Create / Cancel buttons. Their content
  now scrolls and the buttons always stay visible.
- The one-line installer (`curl … | bash`) stopped after "Base packages"
  because apt read the rest of the piped script from stdin. The script now runs
  inside a function, so it is read completely before anything executes.

### Changed
- CI can also be started manually (workflow_dispatch).

## [1.3.0] - 2026-11-07

### Added
- **Update notice**: once a day the app checks GitHub for a newer release and
  shows a bar with **Update** (downloads and installs the new `.deb`),
  **What's new** and **Skip this version**. It can be turned off in
  Preferences. The terms of use now mention this check.
- **Continuous integration** (GitHub Actions): every push compiles the code,
  checks translations, runs the script tests, builds the `.deb` and installs it
  on a clean Ubuntu 24.04 container to make sure the app starts.
- Screenshots in the README.

### Fixed
- `install.sh --local` failed on a clean system because `fakeroot` was missing;
  it is no longer required to build the package.
- After changing the language, the replaced window could raise an error when a
  pending refresh arrived.
- Git tab: long file names now keep the name visible and trim the folder.

### Verified
- The full installer was run on a clean Ubuntu 24.04: it installs Docker, DDEV,
  mkcert and Stackyard, and the app starts.

## [1.2.0] - 2026-11-07

### Added
- **Code** tab: a built-in editor for each project.
  - File explorer: new file/folder, rename (F2), copy (Ctrl+C), cut (Ctrl+X),
    paste (Ctrl+V), duplicate (Ctrl+D), move to trash (Delete), copy path and
    open in the file manager. Folders load on demand.
  - Tabbed editor (GtkSourceView) with syntax highlighting for PHP, Blade,
    JavaScript/TypeScript, Vue, CSS, HTML, JSON, YAML, SQL, Markdown, `.env`
    and more; line numbers, current-line highlight, bracket matching and smart
    indentation. The colour scheme follows the light/dark theme.
  - Find (Ctrl+F) and replace (Ctrl+H) with match case and regular expressions,
    quick open by name (Ctrl+P, respects `.gitignore`), save (Ctrl+S) and close
    (Ctrl+W). Unsaved files are marked with ● and you are asked before closing
    or quitting. Files changed on disk are reloaded.
  - The terminal panel shrinks while the Code tab is open.

## [1.1.0] - 2026-11-07

### Changed
- **New name: Stackyard** (was Panel DDEV) and a new icon: three stacked layers
  (web, PHP, database) with a status light. The name no longer uses the DDEV
  trademark.
- The repository is now `jaayala03/stackyard`, the package and command are
  `stackyard`, and the installer downloads from the new repository. Installing
  the `stackyard` package replaces `panel-ddev` automatically.
- Settings and the "Open at login" entry of Panel DDEV are migrated on first run.

## [1.0.0] - 2026-11-07

First stable release: everything planned for Panel DDEV 1.0 is in.

### Added
- **Set up Vite** (Quick commands, shown when the project has a
  `vite.config.*`): exposes port 5173 through DDEV in `.ddev/config.vite.yaml`
  and adds the `server` block to `vite.config` (keeping a `.bak`), so
  `npm run dev` and hot reload work at `https://<project>.<tld>:5173`. If the
  config cannot be patched safely, the snippet to paste is shown instead.

### Changed
- The "Resources" row moved to the end of the project configuration.

### Highlights since 0.1.0
Projects (new, clone, add folder, settings), tray icon, English/Spanish UI,
light/dark theme, Git tab (stage, diff, history, commit, branches, pull/push,
stash, discard, conflicts), GitHub repository picker, quick commands, database
import/export and snapshots, Xdebug switch, .env editor, sharing via public
link, notifications, resource usage and auto-stop of idle projects.

## [0.13.0] - 2026-11-07

### Added
- **Resource usage**: memory per project in the list, CPU and RAM in the
  project configuration, and the total used by DDEV in the header.
- **Stop idle projects** (Preferences): stop a running project automatically
  after 30 minutes, 1 hour or 2 hours without web traffic or CPU use, while the
  app is open. A notification tells you when it happens. Off by default.

## [0.12.0] - 2026-11-07

### Added
- Git tab:
  - **Discard changes** of a file (right-click → Discard changes…), with
    confirmation. Works for modified, new, added and renamed files.
  - **Stash** menu: save your changes aside (including new files) with an
    optional description, then apply, pop or delete each stash.
  - **Conflict resolution**: a banner appears during a merge, rebase or
    cherry-pick with the number of conflicted files. Right-click a file to use
    your version, their version or mark it as resolved, then **Continue** or
    **Abort**.
  - **Pull (merge)** and **Pull (rebase)** next to the regular fast-forward pull.

## [0.11.0] - 2026-11-07

### Added
- **Desktop notifications** when an action finishes (success or failure);
  clicking one opens the app. Preferences → Notifications: when the window is
  not in focus (default), always or never.

### Fixed
- Failed actions were reported as successful (✔ on the tab) because the exit
  code of the cleanup step replaced the script's. Covered by a new test.

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
