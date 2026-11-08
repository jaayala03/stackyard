# Panel DDEV

Interfaz gráfica (Python + GTK 3) para gestionar proyectos [DDEV](https://ddev.com) en Linux,
al estilo de Laragon.

## Qué hace

- **Lista** todos tus proyectos DDEV con su estado (se actualiza cada 10 s).
- **Iniciar / Detener / Reiniciar**, abrir en el navegador, abrir la carpeta o tu editor.
- **Nuevo proyecto**: tipo (PHP, Laravel, WordPress, Symfony, Drupal…), PHP, Node,
  Apache/nginx y base de datos. Puede descargar el framework automáticamente.
- **Clonar con git**: URL y rama; configura DDEV, arranca e instala dependencias
  (`composer install`, `npm install`, `.env` + `APP_KEY` en Laravel).
- **Cambiar configuración** de un proyecto existente (incluye migrar MariaDB ↔ MySQL).
- **Herramientas**: terminal dentro del contenedor, logs en vivo, phpMyAdmin
  (lo instala si falta), Mailpit, importar/exportar la base de datos.
- **Apagar todo** (`ddev poweroff`) y **Eliminar** (borra contenedores y BD, no tus archivos).

Cada acción se ejecuta en una pestaña de terminal integrada: ves exactamente qué
comandos de `ddev` se lanzan, y si alguno pide la contraseña (p. ej. para añadir un
dominio `.local` a `/etc/hosts`) la escribes ahí mismo.

## Uso

```bash
./panel-ddev
```

También aparece en el menú de aplicaciones como **Panel DDEV**
(`~/.local/share/applications/panel-ddev.desktop`).

## Requisitos

Docker, DDEV, `python3-gi`, `gir1.2-vte-2.91` y `python3-yaml` (vienen en Linux Mint).

## Estructura

| Archivo | Para qué |
|---|---|
| `panel_ddev/ddev.py` | Habla con `ddev` y genera los scripts de cada acción |
| `panel_ddev/app.py` | Ventana principal |
| `panel_ddev/dialogs.py` | Diálogo de nuevo / clonar / configurar |
| `panel_ddev/terminal.py` | Pestañas de terminal integradas (VTE) |

Valores por defecto (PHP 8.4, Node 24, Apache, MariaDB 11.8) en `DEFAULTS` de `ddev.py`.
