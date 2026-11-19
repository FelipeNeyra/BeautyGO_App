# BeautyGO

Proyecto Django de gestión de citas y servicios de RG Beauty. Este documento describe cómo preparar el proyecto y programar el respaldo comprimido, cifrado con GnuPG y almacenado en Backblaze B2.

## Funciones Principales

- Módulo de Autenticación y Roles: Permite el registro diferenciado e inicio de sesión seguro para Clientes, Proveedores y la Administradora, aplicando control de acceso basado en roles (RBAC).
- Catálogo y Reserva de Servicios: Los clientes pueden explorar servicios de belleza, filtrar por especialidad o ubicación y agendar horas directamente según la disponibilidad del proveedor.
- Panel de Gestión para Proveedores: Interfaz donde los prestadores de servicios pueden dar de alta sus especialidades, ajustar tarifas, gestionar horarios de atención y aceptar o rechazar reservas.
- Panel de Administración: Control centralizado para supervisar el rendimiento de la plataforma, gestión de cuentas de proveedores y control de suscripciones bajo modelo SaaS.

### Composición y Conexión

1. Base de Datos — MySQL: Modelada, diseñada y administrada mediante MySQL Workbench, permitiendo estructurar esquemas relacionales óptimos para el almacenamiento seguro de usuarios, tablas transaccionales de reservas, perfiles de prestadores y catálogos de servicios.
2. Creación de Modelo de Datos: Incorporado y actualizado mediante migraciones (`migrations`) almacenadas en el directorio `/website/migrations`. Requiere una conexión previa y efectiva con un esquema de datos creado en MySQL Client.
3. Registro y Login: Implementados mediante la líbreria `auth-user` nativa de framework **Django**. Permite la creación y validación de datos de registro para nuevos usuarios. Las contraseñas siempre se hashean meidante PBKDF2 con SHA-256 y salt aleatorio para cada usuario. El Inicio de Sesión valida por medio de correo asociado y contraseña (nunca se revela).
4. Registro de datos y operaciones CRUD: Se hace uso de multiples formularios creados en `forms.py`para la creación de nuevos registros para las entidades y/o modelos establecidos para el Modelo de Datos. Se presentan y hacen operativos por medio de vistas incorporadas en `views.py`.
5. Respaldo de Datos: Asociado y almacenado por medio de un `bucket` (Contenedor de datos) creado en Blackblaze B2 Storage Service y cifrado mediante la herramienta `GnuPG` para garantizar su descifrado solo por parte de usuarios asociados.

## Requisitos

### Programas para Windows

- Python compatible con Django 5.2.
- Cliente MySQL (MySQL Community Server o MySQL Client Tools). El respaldo requiere `mysqldump.exe`; agrega su carpeta `bin` al `PATH`. Para restaurar también se requiere `mysql.exe`.
- GnuPG. Agrega la carpeta de `gpg.exe` al `PATH`.
- Una instancia MySQL accesible con la base de datos del proyecto y un usuario autorizado para respaldarla.

Comprueba desde una terminal nueva que estén disponibles:

```powershell
python --version
mysqldump --version
gpg --version
```

**Nota**: `gpg.exe`suele agregarse automaticamente al `PATH` después de haber instalado GnuPG en el sistema. El Cliente MySQL (y `mysql.exe` junto a él) deben agregarse manualmente por el usuario.

### Librerías Python

`requirements.txt` instala estas dependencias:

- `Django`: Framework de la aplicación.
- `mysqlclient`: Adaptador MySQL usado por Django.
- `django-dbbackup`: Comandos para respaldar y restaurar bases de datos.
- `django-storages[s3]` y `boto3`: Almacenamiento S3 compatible usado para enviar respaldos a B2.
- `python-gnupg`: Integración Python con GnuPG para cifrar los respaldos.

Desde la raíz del proyecto instala las dependencias en el mismo intérprete que usará la tarea:

```powershell
python -m pip install -r requirements.txt
```

## Preparar la configuración local

1. Copia la plantilla excluida de variables (`configuracion_entorno.py`) a un archivo local (Incorporar el archivo propio también sirve):

   ```powershell
   Copy-Item .\configuracion_entorno.example.py .\configuracion_entorno.py
   ```
2. Edita y/o verifica `configuracion_entorno.py` y completa los valores de `DB_PASSWORD`, `B2_ACCESS_KEY_ID`, `B2_SECRET_ACCESS_KEY`, `DBBACKUP_GPG_RECIPIENT` y `GNUPGHOME`. Configura también `DB_NAME`, `DB_USER`, `DB_HOST`, `DB_PORT`, `B2_BUCKET_NAME` y `B2_REGION_NAME` si no corresponden a los valores de ejemplo establecidos en `settings.py`. El ejecutor carga este archivo al iniciar.
3. Obtén la clave pública del destinatario del respaldo y su huella primaria. En el equipo que creó la clave puedes exportar **solo la parte pública** mediante el siguiente comando:

   ```powershell
   gpg --armor --export HUELLA_PRIMARIA > .\destinatario-publico.asc
   ```

   El archivo `destinatario-publico.asc` sera compartido directametne con cada equipo que cifrará respaldos para ese destinatario.
4. En la cuenta de Windows que ejecutará el respaldo, importa la clave pública y comprueba que tenga subclave de cifrado (`[E]`):

   ```powershell
   gpg --import .\destinatario-publico.asc
   gpg --list-keys --list-options show-usage --with-subkey-fingerprint
   gpgconf --list-dirs homedir
   ```

   En `configuracion_entorno.py`, establece `DBBACKUP_GPG_RECIPIENT` con la huella de la clave primaria destinataria otorgada por `gpg`(Corresponde a un valor hexádecimal de 40 caracteres) y `GNUPGHOME` con la ruta del llavero que devuelve `gpgconf --list-dirs homedir`. La ruta de GnuPG es local a cada equipo.

El archivo `configuracion_entorno.py` está excluido de Git. Copias con los valores de seguridad necesarios serán compartidos directamente con los usuarios y grupos de trabajo necesarios.

## Probar y programar el respaldo

1. Desde la raíz del proyecto, ejecuta primero una prueba manual:

   ```powershell
   python ejecutar_respaldo.py
   ```

   El ejecutor valida la configuración, `mysqldump`, GnuPG, `python-gnupg` y la capacidad de cifrado de la clave antes de iniciar. El resultado esperado incluye un archivo con nombre terminado en `.dump.gz.gpg` y su archivo `.metadata`, almacenados en el bucket B2.
2. Configura la zona horaria de Windows como Santiago con ajuste automático de horario de verano. La tarea usa la hora local de Windows.
3. Registra la tarea diaria a las 21:00 desde PowerShell:

   ```powershell
   .\programar_respaldo_diario.ps1
   ```

   El script crea `BeautyGO-Respaldo-MySQL` para ejecutar `ejecutar_respaldo.py` cada día. Usa la cuenta actual y requiere que su sesión permanezca iniciada. `StartWhenAvailable` permite iniciar una ejecución atrasada cuando el equipo vuelva a estar disponible; no enciende por sí mismo un equipo apagado.
4. Revisa el resultado de la tarea:

   ```powershell
   Get-ScheduledTaskInfo -TaskName "BeautyGO-Respaldo-MySQL" |
     Select-Object LastRunTime, NextRunTime, LastTaskResult
   ```

   Un `LastTaskResult` igual a `0` indica que la última ejecución terminó correctamente. Comprueba también la presencia del archivo cifrado y sus metadatos en el bucket B2.

## Ejecutar el Proyecto

1. Mediante una terminal ejecutada en la raíz del proyecto, crear una nuevo entrono virtual para el almacenamiento de librerías a instalar y ejecución local del proyecto:

   ```cmd
   python -m venv env
   ```

   A contnuación, instalar las librerías establecidas en el archivo `requirements.txt`

   ```cmd
   pip install -r requirements.txt
   ```
2. Incorporar las migraciones establecidas:

   ```cmd
   python manage.py migrate
   ```

   Debe haberse creado un esquema nuevo en la base de datos MySQL Client por medio de la terminal CLI de usuario o mediante la herramienta gráfica MySQL Workbench. El esquema debe tener el mismo nombre que el valor establecido para `DB_NAME`.
3. Para comprobar la correcta migración de cambios y conexión efectiva con el esquema de base de datos, ejecutar el siguiente comando de arranque:

   ```cmd
   python manage.py runserver
   ```

   El mismo permite ejeuctar e iniciar el sistema de forma local mediante `localhost` y debe mostrar en pantalla la platorma gráfica operativa en caso de haber sido efectiva la conexión con MySQL.

## Navegación mediante Roles

- Cliente: Requiere crearse una nueva cuenta de usuario mediante el botón `CREAR CUENTA` para luego poder hacer reservas de servicios ofrecidos y cambiar información de su cuenta de usuario.
- Prestador: Obligatoriamente debe ingresar como cliente para poder postular como posible prestador. Su postulación debe ser validada por la administración de la plataforma. En caso de haber sido validada, podra ingresar al panel de prestadores por medio del botón `PRESTADOR` presente en la barra de navegación.
  Como prestador, puede ofrecer múltiples servicios, confirmar o rechazar reservar de distintos clientes y pagar su suscripción a la plataforma dependiendo del periodo de tiempo (mes actualmente cursando) correspondiente.
- Administrador: Posee una interfaz propia de gestión. Puede validar o rechazar solicitudes de distintos prestadores recibidas, verificar el estado presente de las suscripciones correspondientes a prestadores ya validados (Pudiendo confirmar su pago de forma manual) y llevar a cabo el pago de liquidaciones (simuladas al no haber ningúna pasarela de pago asociada).
  **Nota**: No se dispone de ningún panel o sección para la creación de un usuario administrador. Para llevar a cabo la creación de un administrador nuevo, deben seguirse los pasos a continuación:
  1. Crear un nuevo usuario desde la vista principal de la aplicación mediante el botón `CREAR CUENTA`y rellenando los campos del formulario.
  2. Acceder a las tablas creadas en el esquema local creado en MySQL y accesible desde MySQL Workbench.
  3. Seleccionar la tabla u entidad de nombre `administrador`para insertar nuevos registros.
  4. Ejecutar un query con la siguiente estructura: `INSERT INTO administrador VALUES (1, "administrador", "id de usuario creado");`, para así crear un nuevo administrador asociado con el nuevo usuario creado.
  5. Para acceder como administrador, iniciar sesión de forma normal mediante correo y contraseña.
