# Términos de uso

Última actualización: 7 de noviembre de 2026 · [English version](TERMS.md)

Al descargar, instalar o usar **Stackyard** («la aplicación») aceptas estos términos.
Si no estás de acuerdo, no la uses.

## 1. Licencia

La aplicación es software libre y gratuito distribuido bajo la
[licencia MIT](LICENSE). Puedes usarla, copiarla, modificarla y redistribuirla,
también con fines comerciales, siempre que conserves el aviso de copyright y el
texto de la licencia. Si hay diferencias entre este documento y la licencia MIT,
prevalece la licencia MIT.

## 2. Sin garantía

La aplicación se ofrece **«tal cual»**, sin garantías de ningún tipo, expresas o
implícitas, incluidas las de comerciabilidad, idoneidad para un fin concreto o
ausencia de errores.

## 3. Limitación de responsabilidad

En la máxima medida permitida por la ley, los autores no son responsables de
ningún daño directo o indirecto derivado del uso de la aplicación, incluida la
pérdida de datos. Ten en cuenta que algunas acciones son **destructivas por
diseño** y la aplicación te pide confirmación antes de ejecutarlas:

- **Eliminar proyecto** borra los contenedores y la base de datos del proyecto.
- **Importar base de datos** y **Restaurar copia** reemplazan la base de datos actual.
- **Descartar cambios** en la pestaña Git borra modificaciones no guardadas en un commit.

Haz copias de seguridad de lo que te importe.

## 4. Software de terceros

La aplicación es una interfaz sobre herramientas de terceros que se instalan y
rigen por sus propias licencias y condiciones, entre otras:
[DDEV](https://github.com/ddev/ddev) (Apache 2.0), [Docker](https://www.docker.com/legal/),
[git](https://git-scm.com/) (GPL 2.0), [mkcert](https://github.com/FiloSottile/mkcert) (BSD-3),
GTK y VTE (LGPL), y las imágenes de contenedor que descarga DDEV (PHP, MariaDB,
MySQL, PostgreSQL, phpMyAdmin, etc.). Usarlas a través de la aplicación implica
aceptar sus respectivas condiciones.

## 5. Marcas

«DDEV», «Docker», «GitHub», «Laravel», «WordPress» y otros nombres citados son
marcas de sus respectivos titulares. **Stackyard es un proyecto independiente y
no está afiliado, patrocinado ni respaldado por el proyecto DDEV ni por ninguna
de esas empresas.**

## 6. Privacidad

La aplicación **no recopila, almacena ni envía datos personales ni de uso** a sus
autores. Todo se ejecuta en tu equipo. Algunas funciones se conectan a servicios
externos solo cuando tú las usas:

- **GitHub** (clonar, pull, push, listar tus repositorios) mediante tu sesión de `git`/`gh`.
- **Compartir proyecto** crea un enlace público temporal a través del proveedor
  que configure DDEV (p. ej. Cloudflare o ngrok). Cualquiera con el enlace podrá ver
  tu sitio mientras esté activo.
- **Descarga de imágenes y paquetes** (Docker Hub, Packagist, npm, etc.).
- **Búsqueda de actualizaciones**: una vez al día la app pregunta a la API de
  GitHub cuál es la última versión. Solo se envía la petición (ningún dato
  personal). Puedes desactivarlo en Preferencias.

Esos servicios tratan los datos según sus propias políticas de privacidad.

## 7. Cambios

Estos términos pueden actualizarse. La versión vigente es la publicada en el
repositorio junto a cada versión de la aplicación.

## 8. Contacto

Dudas, errores o sugerencias: abre un *issue* en el repositorio del proyecto.
