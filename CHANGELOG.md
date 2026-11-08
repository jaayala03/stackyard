# Cambios

Todas las versiones publicadas de Panel DDEV. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y las versiones
siguen [SemVer](https://semver.org/lang/es/).

## [0.2.0] - 2026-11-07

### Añadido
- Pestaña **Git** en cada proyecto: cambios con casillas para prepararlos,
  diferencias con colores, historial de commits, commit (Ctrl+Enter), cambiar y
  crear ramas, fetch, pull y push. Si el proyecto no usa git, permite inicializarlo.
- Paquete **.deb** e instalador `instalar.sh`, que deja Docker, DDEV, mkcert y la
  app listos en un solo paso.
- Ventana **Acerca de** con versión, licencia y términos.
- Licencia MIT y términos de uso.

## [0.1.0] - 2026-11-07

### Añadido
- Lista de proyectos DDEV con su estado, iniciar, detener, reiniciar y apagar todo.
- Crear proyectos nuevos (PHP, Laravel, WordPress, Symfony, Drupal…) eligiendo
  PHP, Node, Apache/nginx y base de datos.
- Clonar repositorios con git, configurar e instalar dependencias.
- Cambiar la configuración de un proyecto (incluye migrar MariaDB ↔ MySQL).
- Herramientas: terminal en el contenedor, logs, phpMyAdmin, Mailpit,
  importar/exportar base de datos, composer y npm install.
- Terminal integrada donde se ve cada acción.
