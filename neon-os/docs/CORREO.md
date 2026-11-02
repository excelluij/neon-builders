# Verificación de correo y acceso de administrador: configuración y despliegue

Neon OS envía un **código de 6 dígitos** al correo de cada persona que se registra. Mientras no lo escriba, la cuenta no puede iniciar sesión.
Todo lo secreto (las claves del correo) vive **fuera del código**: en un archivo `.env` junto a la app (que Git ignora) o en las variables de entorno de Windows; nunca en el código fuente ni en archivos que se suban a Git. Las contraseñas de los administradores no están en ningún archivo: cada administrador crea la suya en su primer acceso ([sección 2](#administradores-y-código-de-profesor)).

> **Estado de esta entrega:** el envío está implementado y probado con un servidor SMTP *simulado*. **Nunca se probó contra un proveedor real**
> porque eso requiere tus credenciales. Los pasos de abajo (sobre todo el [paso 4](#4-probar-el-envío-real)) son los que lo comprueban de verdad.
> Lee también la [sección 9](#9-límites-de-seguridad-que-debes-conocer): la verificación vive en la propia app y tiene límites.

## 0. Instalar las dependencias y arrancar

`requirements.txt` fija las bibliotecas de terceros que usa la app de escritorio, con las versiones con las que se probó (Python 3.10): `customtkinter`, `pillow` y `requests`. Lo recomendable es un entorno virtual dentro de esta carpeta (así no se tocan los demás programas de Python de tu equipo):

```powershell
python -m venv .venv
```

```powershell
.venv\Scripts\python -m pip install -r requirements.txt
```

Y para arrancar la app:

```powershell
.venv\Scripts\python APP_final.py
```

Los comandos de consola `correo.py` y `almacen.py` usan solo la biblioteca estándar: funcionan con cualquier Python, sin instalar nada. El prototipo móvil `app_movil.py` necesita además la biblioteca `flet`, que no forma parte de `requirements.txt`.

### Logo y programa `NeonOS.exe`

El logo de Neon OS es `logo.png`. De él salen `logo_app.png` (recortado y con fondo transparente, se ve en la pantalla de acceso) y `logo.ico` (icono de las ventanas, de la barra de tareas y del `.exe`); si cambias `logo.png`, vuelve a generarlos con `python preparar_logo.py`. Para construir el `.exe` (hace falta `pyinstaller` en el entorno: `.venv\Scripts\python -m pip install pyinstaller`):

```powershell
.\construir_exe.ps1
```

Deja el resultado en `dist_exe\NeonOS\`. El `.exe` lleva dentro el código y el logo; el `.env`, `neon_os.db`, `nexus_cloud_data.db` y la carpeta `materiales_neon` **van junto a `NeonOS.exe`** y no se incluyen. Para actualizar una instalación que ya existe copia solo `NeonOS.exe` y la carpeta `_internal` (con el programa cerrado) y conserva esos archivos.

## 1. Cómo funciona (resumen)

| Regla | Valor |
|---|---|
| Código | 6 dígitos, guardado con hash (nunca en claro) |
| Código de profesor | Solo para profesores: llega **en el mismo correo** que el código de 6 dígitos. Es **aleatorio y único** (formato `XXXXX-XXXXX`, nunca se entrega el mismo a dos personas) y solo se guarda su huella. Para activar la cuenta se escriben **los dos** códigos: si falla uno, no vale ninguno y cuenta un solo intento. Un reenvío trae un código de profesor nuevo |
| Administradores | Dos cuentas predeterminadas (`luisbaco2005@gmail.com` y `dsandovaltorres05@gmail.com`; el usuario es el propio correo). Nacen **sin contraseña**: en el primer acceso reciben el código en ese correo y, junto con él, **crean su contraseña** (mínimo 8 caracteres) |
| Vigencia | 10 minutos |
| Intentos | máximo 5 por código |
| Reenvío | como mínimo cada 60 segundos |
| Tope de códigos | máximo de 5 códigos por cuenta sin verificar (el inicial + 4 reenvíos); después hay que cancelar y volver a registrarse |
| Cuentas nuevas | sin verificar: no pueden iniciar sesión (y no aparecen en el ranking) |
| Cuentas que ya existían | quedan verificadas (no se les pide nada) |
| Correo repetido | un correo (verificado o pendiente) no se puede registrar dos veces |
| Pendientes viejos | las cuentas sin verificar con más de 24 h desde que se crearon se borran solas al registrarse alguien (reenviar el código no las mantiene vivas) |

Si el correo **no está configurado**, el registro falla de forma segura y **no crea la cuenta**: «El envío de correos no está configurado. Avisa al administrador.»

## 2. Variables de entorno

### Dónde se definen: archivo `.env` o variables de Windows

Los nombres de abajo se pueden dar de dos maneras (las dos funcionan a la vez):

1. **Archivo `.env`** (recomendado): un archivo de texto llamado exactamente `.env`, **junto a `APP_final.py`** (en la misma carpeta que `correo.py`). Copia `.env.example` con ese nombre, quita el `# ` de las líneas que necesites y escribe tus valores. La app lo lee **al arrancar** (y también `python correo.py ...`, `python almacen.py ...` y `app_movil.py` al ejecutarse), no hace falta abrir una terminal nueva.
2. **Variables de entorno de Windows** (`setx`, ver la [sección 3](#3-configurar-un-proveedor)).

Reglas del `.env`:

- Una variable por línea: `NOMBRE=valor` (con `export ` delante también vale). Los comentarios van **solo en líneas que empiezan por `#`**: no hay comentarios al final de una línea, así que una clave puede llevar `#` o `=` sin problema.
- Un valor entre comillas (simples o dobles) pierde las comillas; úsalas si el valor empieza o termina con espacios.
- **Lo ya definido en las variables de Windows tiene prioridad**: el `.env` solo rellena lo que falta. Si cambias un valor en el `.env` y no se nota, revisa que no esté definido también con `setx`.
- Solo se leen nombres que empiezan por `NEON_`; cualquier otro (`PATH`, etc.) se ignora y se avisa por nombre, para que un `.env` nunca pueda cambiar variables del sistema. Un valor vacío cuenta como no definido; si una variable se repite, gana la última línea.
- El archivo debe estar en UTF-8 y llamarse `.env`. Ojo: el Explorador de Windows suele ocultar extensiones y puede dejarlo como `.env.txt`; `python correo.py --config` lo detecta y lo avisa (`.env.txt` no se lee).
- Nunca se muestra ningún valor: los avisos hablan de nombres y de números de línea.
- Las pruebas automáticas **no leen** tu `.env` (solo se lee al arrancar como programa).

`.gitignore` (en esta carpeta) excluye `.env` y `.env.*` (pero **no** `.env.example`, que es la plantilla sin secretos), `*.db`, `__pycache__/` y `.venv/`. Para comprobarlo: `git check-ignore -v .env` debe mostrar la regla. Importante: en este equipo el repositorio de Git tiene su raíz en `C:\Users\user` (tu carpeta de usuario), así que ese `.gitignore` solo protege esta carpeta; **no ejecutes `git add .` ni `git add -A` desde tu carpeta de usuario**, y si quieres versionar el proyecto crea el repositorio dentro de esta carpeta (`git init` aquí).

### Correo (SMTP)

| Variable | ¿Obligatoria? | Qué es |
|---|---|---|
| `NEON_SMTP_HOST` | sí | Servidor SMTP del proveedor (Brevo: `smtp-relay.brevo.com`) |
| `NEON_SMTP_USUARIO` | sí | Usuario/login SMTP que te da el proveedor |
| `NEON_SMTP_CLAVE` | sí | Clave SMTP del proveedor (en Brevo es una «clave SMTP», **no** la contraseña de tu cuenta) |
| `NEON_SMTP_REMITENTE` | sí | Remitente ya verificado en el proveedor, p. ej. `Neon OS <no-responder@tudominio.com>` |
| `NEON_SMTP_PUERTO` | no | Por defecto `587` (STARTTLS) o `465` si la seguridad es `ssl` |
| `NEON_SMTP_SEGURIDAD` | no | `starttls` (por defecto) o `ssl` |
| `NEON_SMTP_TIMEOUT` | no | Segundos de espera al servidor, un número positivo (por defecto `15`) |
| `NEON_CORREO_MODO` | no | `smtp` (por defecto) o `consola` (solo desarrollo, ver [sección 5](#5-modo-desarrollo-sin-enviar-correos)) |

Solo se aceptan destinatarios con direcciones ASCII sencillas (`nombre@dominio.com`): no se admiten comentarios entre paréntesis, comillas, espacios ni letras acentuadas.

### Administradores y código de profesor

**Ya no hay `NEON_ADMIN_CLAVE`, `NEON_ADMIN_USUARIO`, `NEON_ADMIN_CORREO` ni `NEON_CODIGO_PROFESOR`**: no hace falta configurar nada para que existan el acceso de administrador y el registro de profesores (los mensajes «define NEON_ADMIN_CLAVE…» y «define NEON_CODIGO_PROFESOR…» desaparecieron). Solo se necesita el correo (`NEON_SMTP_*`), porque ahora los códigos llegan por ahí.

**Administradores.** Las dos cuentas de `almacen.ADMINISTRADORES` se crean solas al iniciar la app (si ya existen no se tocan). Para entrar la primera vez:

1. En la pantalla de acceso elige **Administrador**, escribe tu **correo** en «Usuario» y pulsa *Iniciar Sesión* (con cualquier contraseña: todavía no tienes).
2. La app te lleva a «Activa tu cuenta de administrador». Pulsa **Enviar código**: llega un código de 6 dígitos a ese correo.
3. Escribe el código, **crea tu contraseña** (mínimo 8 caracteres, dos veces) y pulsa **Activar cuenta**.
4. Desde entonces entras con tu correo y tu contraseña, sin volver a pedir código.

Detalles: el código vale 10 minutos y tiene 5 intentos; los administradores **no tienen tope de envíos** (solo la espera de 60 s) porque sus correos son públicos y un tope dejaría a cualquiera bloquearles el acceso; una cuenta de administrador no se puede cancelar ni caduca. Nadie puede registrarse con el correo ni el nombre de un administrador.

**Si el correo no funciona** (por ejemplo Brevo rechaza esta conexión, ver la [sección 6](#6-si-algo-falla)), pon la contraseña desde la consola de quien tiene la carpeta de la app (con la app cerrada; pide la contraseña sin mostrarla):

```powershell
python almacen.py --clave-admin luisbaco2005@gmail.com
```

**Olvidé mi contraseña:** no hay recuperación por correo. Con ese mismo comando quien tenga la carpeta de la app pone una nueva.

**Profesores.** Al registrarse eligen *Profesor* y rellenan usuario, correo, contraseña y materia (ya **no** hay campo de código). La app les envía **un solo correo** con dos códigos: el de verificación (6 dígitos) y su **código de profesor**, único y aleatorio. En la pantalla de verificación escriben los dos (el de profesor vale en mayúsculas o minúsculas, con o sin guion). Si piden un reenvío, los dos códigos cambian y los anteriores dejan de valer. Ningún mensaje de la pantalla muestra los códigos y en la base solo queda su huella.

> **Ojo con lo que esto cambia:** antes solo se registraba como profesor quien conocía un código secreto que tú repartías. Ahora **cualquiera con un correo propio puede registrarse como profesor**: el código de profesor llega al mismo correo que el de verificación, así que confirma que es suyo, pero no que sea un profesor de verdad. Si quieres volver a filtrar quién puede ser profesor (por ejemplo, que tú aprobaras cada cuenta o una lista de correos permitidos), habría que añadirlo.

### Cuentas de demostración

| Variable | ¿Obligatoria? | Qué es |
|---|---|---|
| `NEON_DEMO_CLAVE` | no (**solo desarrollo**) | Si la defines (mínimo 8 caracteres), una base **sin personas inscritas** recibe las cuentas de demostración `camilo` (profesor) y `daniel` (estudiante) con esa clave |

- Antes el código de profesores estaba escrito en `APP_final.py` y las cuentas de demostración se creaban siempre con una clave fija de tres dígitos. **Ya no hay ni código ni clave en el código fuente**.
- Sin `NEON_DEMO_CLAVE` una base nueva no trae ninguna cuenta (salvo los dos administradores, sin contraseña): crea las cuentas reales registrándote (con el correo configurado) o, solo para desarrollar, usa `NEON_CORREO_MODO=consola`.
- Una `NEON_DEMO_CLAVE` demasiado corta (menos de 8 caracteres) no crea nada y avisa en la consola, sin mostrar la clave.

#### Primer arranque (lista de comprobación)

1. Instala las dependencias ([sección 0](#0-instalar-las-dependencias-y-arrancar)). Escribe en tu `.env` (o define con `setx`) las variables `NEON_SMTP_*` (ver la [sección 3](#3-configurar-un-proveedor)); con `setx` hay que abrir una terminal nueva.
2. En un primer arranque con una base nueva solo existen los dos administradores, sin contraseña: cada uno hace su primer acceso (arriba). Los estudiantes y profesores se registran y verifican su correo.
3. En una instalación que ya existe, retira las cuentas de demostración antiguas (siguiente apartado).

#### Dejar la base sin personas inscritas (empezar de cero)

Para borrar a **todas las personas inscritas** (estudiantes y profesores, con su progreso, sus verificaciones pendientes, los ocultos del ranking y los códigos de profesor ya entregados) y que desde ahí todo el mundo se inscriba con la verificación de correo. Con la app **cerrada**:

```powershell
python almacen.py --reiniciar-personas
python almacen.py --reiniciar-personas --si
```

El primero solo dice cuántas personas borraría. El segundo las borra y **antes guarda una copia** junto a la base (`neon_os_copia_antes_de_reiniciar_AAAAMMDD-HHMMSS.db`). Se conservan las **misiones** publicadas y los dos administradores (vuelven a quedar sin contraseña: otra vez primer acceso). Para otra base, define `NEON_DB` con su ruta. Si alguien dejó la app abierta durante el reinicio, al cerrarla guarda su progreso de nuevo; por eso un registro nuevo con un nombre que tuvo una cuenta anterior siempre empieza de cero.

#### Retirar las cuentas de demostración antiguas de una base que ya existe

Las bases creadas con versiones anteriores ya tienen las cuentas `camilo` y `daniel` con la clave antigua; quitar la semilla del código no las borra. Con la app **cerrada**:

```powershell
python almacen.py --cuentas-demo
python almacen.py --retirar-cuentas-demo --si
```

El primero solo lista cuáles siguen aceptando la clave antigua (no modifica nada). El segundo las borra **junto con su progreso**, y solo a las que aún tienen esa clave: una cuenta cuya clave ya cambió, o cualquier otra cuenta, no se toca. Sin `--si` solo avisa qué retiraría. Haz antes una **copia de neon_os.db**.

### Otras

| Variable | Para qué sirve |
|---|---|
| `NEON_DB` | Ruta alternativa del archivo `neon_os.db` (también la usan `python almacen.py --cuentas-demo`, `--retirar-cuentas-demo`, `--reiniciar-personas` y `--clave-admin`). Ver la advertencia sobre carpetas compartidas en la [sección 8](#8-antes-de-actualizar-una-instalación-que-ya-existe) |
| `NEON_PRUEBA_CORREO_DESTINO` | Solo para la prueba de integración real: a qué dirección enviar el correo de prueba |

## 3. Configurar un proveedor

Funciona con cualquier proveedor que ofrezca SMTP. Los pasos exactos de los menús pueden cambiar; revisa la ayuda del proveedor.

### Ejemplo: Brevo

1. Crea una cuenta en Brevo y **verifica un remitente** (una dirección tuya, o un dominio propio: ver [sección 7](#7-entrega-y-spam)).
2. En la cuenta, abre la sección **SMTP y API → SMTP** y anota el *servidor* (`smtp-relay.brevo.com`), el *puerto* (`587`) y el *login* SMTP.
3. Genera una **clave SMTP** nueva y cópiala en ese momento (después ya no se muestra completa). Usa una clave **solo para Neon OS**: así puedes revocarla sin afectar nada más.
4. Escribe los valores en tu archivo `.env` (copia de `.env.example`, junto a `APP_final.py`); **cambia lo que está entre `<...>` por tus valores reales**:

```
NEON_SMTP_HOST=smtp-relay.brevo.com
NEON_SMTP_USUARIO=<tu-login-smtp>
NEON_SMTP_CLAVE=<tu-clave-smtp>
NEON_SMTP_REMITENTE=Neon OS <tu-remitente-verificado@tudominio.com>
```

   No dejes `NEON_CORREO_MODO` en el archivo (con `consola` no se envía nada). **Alternativa sin archivo**: variables de Windows (ejemplo en PowerShell, con los mismos marcadores `<...>`):

```powershell
setx NEON_SMTP_HOST "smtp-relay.brevo.com"
setx NEON_SMTP_USUARIO "<tu-login-smtp>"
setx NEON_SMTP_CLAVE "<tu-clave-smtp>"
setx NEON_SMTP_REMITENTE "Neon OS <tu-remitente-verificado@tudominio.com>"
```

`setx` guarda las variables para tu usuario de Windows, pero **solo las ven las terminales y programas que abras después**: cierra y vuelve a abrir la terminal (o la app) antes de seguir. Otra opción es el panel «Variables de entorno» de Windows.
Solo para probar en la terminal actual, sin guardar nada: `$env:NEON_SMTP_CLAVE = "<tu-clave-smtp>"`.

### Ejemplo: Gmail

Requiere verificación en dos pasos y una **contraseña de aplicación** (no tu contraseña normal). Servidor `smtp.gmail.com`, puerto `587`, usuario = tu dirección de Gmail, remitente = esa misma dirección. Gmail limita mucho los envíos diarios: sirve para pruebas, no para un colegio entero.

## 4. Probar el envío real

Con las variables definidas y una terminal nueva, desde la carpeta del proyecto:

```powershell
python correo.py --config
```

Muestra si se leyó el `.env` (cuántas variables y sus nombres) y qué variables están definidas (**nunca sus valores**). Debe terminar en «✅ Configuración completa».

```powershell
python correo.py --probar tu-correo@ejemplo.com
```

Envía **un correo de prueba real**. Si el proveedor o el cliente de correo fallan, imprime el motivo en lenguaje claro y sin trazas (ver [sección 6](#6-si-algo-falla)). Revisa también la carpeta de spam. Si `NEON_CORREO_MODO=consola` está activo no envía nada: lo dice, y termina con error para que no lo tomes por un envío real.

Prueba automática de integración real (opcional; se salta sola si faltan variables):

```powershell
setx NEON_PRUEBA_CORREO_DESTINO "tu-correo@ejemplo.com"   # y abre una terminal nueva
python pruebas_correo.py -v
```

Las pruebas normales **nunca envían correos reales**: usan un servidor falso. Solo `TestEnvioReal` lo hace, y únicamente si definiste las variables `NEON_SMTP_*` y `NEON_PRUEBA_CORREO_DESTINO`.

## 5. Modo desarrollo (sin enviar correos)

Para programar o probar sin proveedor, pon `NEON_CORREO_MODO=consola` en tu `.env` o, solo para esa terminal:

```powershell
$env:NEON_CORREO_MODO = "consola"
python APP_final.py
```

El código **no se envía**: se imprime en la consola donde corre la app (`[Neon OS · modo desarrollo] Código para …`) y la ventana avisa «modo desarrollo: el código está en la consola». Solo se activa si lo pides con esa variable; **en modo normal un código nunca se muestra ni se registra**. No lo uses en producción: con ese modo cualquiera verifica cualquier correo (ver [sección 9](#9-límites-de-seguridad-que-debes-conocer)).

## 6. Si algo falla

| Mensaje | Qué significa | Qué hacer |
|---|---|---|
| El envío de correos no está configurado… | Faltan variables obligatorias | Define `NEON_SMTP_HOST`, `NEON_SMTP_USUARIO`, `NEON_SMTP_CLAVE`, `NEON_SMTP_REMITENTE` y abre una terminal nueva |
| El proveedor rechazó las credenciales… | Usuario o clave SMTP incorrectos | Revisa el login y genera una clave SMTP nueva |
| El proveedor de correo no permite enviar desde esta conexión (dirección IP no autorizada)… | Brevo tiene activado el bloqueo por IP (*Direcciones IP autorizadas*, error `525 5.7.1 Unauthorized IP address`) y la IP de este equipo no está en su lista. **No es una clave mala.** Como la app se reparte a muchos equipos con IP distintas, una IP puntual no sirve | En Brevo, en *Seguridad → Direcciones IP autorizadas*, **desactiva el bloqueo por IP**. Mientras tanto, el administrador puede poner su contraseña con `python almacen.py --clave-admin correo` |
| El remitente configurado no está autorizado… | El remitente no está verificado en el proveedor | Verifica esa dirección/dominio en el proveedor |
| La dirección de correo fue rechazada… | El proveedor rechazó de forma **definitiva** (código 5xx) la dirección del estudiante | Que revise y escriba de nuevo su correo |
| El proveedor limitó el envío por ahora… | Cupo agotado, límite temporal o rechazo **pasajero** (códigos 4xx: también cuando el buzón de destino responde «inténtalo luego») | Esperar y reintentar, o subir de plan |
| No se pudo conectar con el servidor de correo | Sin internet, puerto bloqueado o `NEON_SMTP_HOST`/`NEON_SMTP_PUERTO`/`NEON_SMTP_SEGURIDAD` mal | Probar `python correo.py --probar …` y revisar el firewall |
| No se pudo enviar el correo por un error inesperado del cliente de correo | Algo no previsto (por ejemplo una clave SMTP con caracteres no ASCII) | Revisa las variables `NEON_SMTP_*` |
| NEON_SMTP_… debe ser… / fuera de rango | Un valor opcional mal escrito (el timeout debe ser un número finito mayor que 0) | Corregir la variable (o borrarla para usar el valor por defecto) |
| Modo desarrollo (NEON_CORREO_MODO=consola): no se envió nada | `--probar` con el modo consola activo | Quita `NEON_CORREO_MODO` (del `.env` y de las variables de Windows) para probar el envío real |
| Se ignoran las variables que no empiezan por NEON_ / la línea N no tiene el formato NOMBRE=valor / Encontré .env.txt pero no .env | Aviso sobre el `.env` (solo nombres y números de línea) | Corrige el archivo según las reglas de la [sección 2](#dónde-se-definen-archivo-env-o-variables-de-windows) |
| Ya se enviaron el máximo de códigos para esta cuenta… | Se llegó al tope de 5 códigos | Cancelar el registro (pide la contraseña) y volver a registrarse más tarde |

Los mensajes nunca incluyen tu clave ni el texto bruto del proveedor.

## 7. Entrega y spam

- Usa un **remitente verificado** en el proveedor. Si envías desde un dominio propio, configura **SPF** y **DKIM** en el DNS del dominio siguiendo las instrucciones del proveedor; sin eso, muchos correos caen en spam.
- La primera vez, pide que revisen la carpeta de spam.
- El plan gratuito de cualquier proveedor tiene un cupo diario de envíos: eso acota cuántos registros y reenvíos caben por día.

## 8. Antes de actualizar una instalación que ya existe

Al primer arranque con esta versión, la app **agrega la columna `verificado` a `neon_os.db`** (y dos columnas más a la tabla de verificaciones) y deja todas las cuentas existentes como verificadas (no pierde datos). Por prudencia, haz una **copia de neon_os.db** antes (copia el archivo a otra carpeta con la app cerrada).

**Si varios equipos comparten el mismo `neon_os.db` (carpeta compartida o `NEON_DB`), actualiza todos los equipos a la vez.** Una copia con la versión anterior no sabe de `verificado`: dejaría entrar cuentas sin verificar, no tendría los administradores predeterminados (seguiría con el acceso por variable de entorno, si estuviera definida), pediría el código de profesor fijo que ya no existe y su registro de usuarios fallaría con un error de la base. Además:

- SQLite sobre una carpeta de red **no garantiza los bloqueos**; con varios equipos escribiendo a la vez pueden aparecer errores «database is locked» o, en el peor caso, datos dañados. Lo más seguro es un solo equipo con la base.
- La vigencia del código (10 min) y la espera de reenvío (60 s) se miden con el reloj de **cada** equipo: mantén la hora sincronizada.

## 9. Límites de seguridad que debes conocer

La verificación sirve para confirmar que una persona **escribió un correo que realmente recibe**, y frena errores y registros de mentira «casuales». **No es a prueba de alguien que controla el equipo** donde corre la app, porque todo (la app, las variables y la base) está en ese equipo:

- Quien controla el equipo puede activar `NEON_CORREO_MODO=consola`, apuntar `NEON_SMTP_HOST` a un servidor propio o editar `neon_os.db` (`UPDATE usuarios SET verificado=1`) y verificar cualquier correo. Una garantía fuerte exigiría un servicio en un servidor, que queda fuera de esta pieza.
- **Las claves en variables de entorno no son secretas para quien use esa sesión de Windows**: cualquiera puede leerlas con `Get-ChildItem Env:`. Y como la app envía los correos ella misma, `NEON_SMTP_CLAVE` tiene que estar en todos los equipos donde alguien se registre. Por eso: usa una clave SMTP **dedicada y revocable** solo para Neon OS (y revócala si sospechas), (las contraseñas de los administradores no están en el entorno: solo viven, con hash, en `neon_os.db`).
- Una cuenta sin verificar **reserva su correo hasta 24 h** desde que se creó (un correo ajeno puede quedar ocupado ese tiempo; quien la creó puede cancelarla con su contraseña). El tope de 5 códigos por cuenta limita el abuso del reenvío; no hay un límite por dirección de correo entre registros distintos.
- **Las claves de administrador antiguas están expuestas.** Estuvieron escritas en el código dos claves de administrador (una en `APP_final.py` y otra en `app_movil.py`, distintas entre sí); ya se quitaron, pero deben considerarse **expuestas** (quedaron en el código y en cualquier copia o historial). El acceso de administrador de `APP_final.py` ya no usa ninguna: cada administrador crea su contraseña nueva en su primer acceso. El prototipo móvil `app_movil.py` conserva su acceso de demostración con `NEON_ADMIN_CLAVE` y `NEON_ADMIN_USUARIO`: si lo usas, elige valores nuevos.
- **Los dos correos de administrador están escritos en el código (`almacen.ADMINISTRADORES`)**: no son secretos, pero quien tenga acceso al código sabe quién es administrador y puede pedir (no activar) códigos a esos buzones. Para activar la cuenta hace falta el código del correo, así que quien no controle ese buzón no puede ponerles contraseña. Si alguien tiene acceso al archivo `neon_os.db` puede cambiar la contraseña editando la base: ver los límites de arriba.
- **El `.env` vive en la carpeta de la app.** Si esa carpeta se comparte (por ejemplo porque `neon_os.db` está en una carpeta compartida), quien la abra puede leer el `.env`: no pongas ahí `NEON_SMTP_CLAVE` en un equipo o carpeta que usen los estudiantes. Git lo ignora, pero Git no protege contra copiar la carpeta, enviarla por correo o subirla a un servicio de archivos.
- No guardes claves en archivos que se suban a Git, ni en capturas ni mensajes (el `.env` es la excepción prevista y está ignorado). Una prueba automática (`pruebas_auth.py`) falla si alguna de las dos claves de administrador antiguas reaparece como texto en los archivos del proyecto.
- **Código de profesores y cuentas de demostración:** ya no hay un código fijo (cada profesor recibe el suyo por correo) ni una clave de demostración en el código (`NEON_DEMO_CLAVE`, ver la [sección 2](#2-variables-de-entorno)). El código antiguo y la clave antigua de demostración deben considerarse expuestos; en una base que ya existe, retira las cuentas demo antiguas con `python almacen.py --retirar-cuentas-demo --si`.
- **Cualquiera con un correo propio puede registrarse como profesor** (ver el aviso de la [sección 2](#administradores-y-código-de-profesor)): el código de profesor demuestra que el buzón es suyo, no que sea docente.
