# Terms of use

Last updated: November 7, 2026 · [Versión en español](TERMINOS.md)

By downloading, installing or using **Stackyard** ("the app") you agree to
these terms. If you do not agree, do not use it.

## 1. License

The app is free software distributed under the [MIT license](LICENSE). You may
use, copy, modify and redistribute it, including for commercial purposes, as
long as you keep the copyright notice and the license text. If anything in this
document conflicts with the MIT license, the MIT license prevails.

## 2. No warranty

The app is provided **"as is"**, without warranty of any kind, express or
implied, including merchantability, fitness for a particular purpose or
freedom from errors.

## 3. Limitation of liability

To the maximum extent permitted by law, the authors are not liable for any
direct or indirect damage arising from the use of the app, including data loss.
Some actions are **destructive by design**, and the app asks for confirmation
before running them:

- **Delete project** removes the project's containers and database.
- **Import database** and **Restore snapshot** replace the current database.
- **Discard changes** in the Git tab removes uncommitted modifications.

Back up anything you care about.

## 4. Third-party software

The app is an interface over third-party tools that are installed and governed
by their own licenses and terms, including:
[DDEV](https://github.com/ddev/ddev) (Apache 2.0), [Docker](https://www.docker.com/legal/),
[git](https://git-scm.com/) (GPL 2.0), [mkcert](https://github.com/FiloSottile/mkcert) (BSD-3),
GTK and VTE (LGPL), and the container images DDEV downloads (PHP, MariaDB,
MySQL, PostgreSQL, phpMyAdmin, etc.). Using them through the app means
accepting their respective terms.

## 5. Trademarks

"DDEV", "Docker", "GitHub", "Laravel", "WordPress" and other names mentioned are
trademarks of their respective owners. **Stackyard is an independent project
and is not affiliated with, sponsored or endorsed by the DDEV project or any of
those companies.**

## 6. Privacy

The app **does not collect, store or send personal or usage data** to its
authors. Everything runs on your computer. Some features connect to external
services only when you use them:

- **GitHub** (clone, pull, push, list your repositories) through your `git`/`gh` session.
- **Share project** creates a temporary public link through the provider DDEV
  is configured with (e.g. Cloudflare or ngrok). Anyone with the link can see
  your site while it is active.
- **Image and package downloads** (Docker Hub, Packagist, npm, etc.).

Those services handle data according to their own privacy policies.

## 7. Changes

These terms may be updated. The applicable version is the one published in the
repository alongside each release of the app.

## 8. Contact

Questions, bugs or suggestions: open an issue in the project repository.
