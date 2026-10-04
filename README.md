# Evento Halloween — Doces ou Travessuras / Dulce o Truco

Bot de Discord en Python con un evento ES y un evento BR independientes en el mismo
servidor. Incluye registro por roles, puertas automáticas, premios de 1–5 dulces,
rankings, panel Staff y persistencia en PostgreSQL. Los datos también se separan por
servidor. Las configuraciones y puntuaciones sobreviven a reinicios.

## Requisitos

- Python 3.11 o posterior; validado localmente con Python 3.14.
- Aplicación y bot en Discord Developer Portal.
- PostgreSQL en Aiven con `DATABASE_URL` y TLS.
- Square Cloud para producción, con variables de entorno configuradas en su panel.

Las versiones comprobadas están fijadas en `requirements.txt`. Las dependencias de
pruebas están separadas en `requirements-dev.txt`.

## Estructura

```text
bot.py                 Inicio, intents, Cogs, Views y apagado
config/                Entorno, IDs y GIFs por idioma
database/              Pool asyncpg, esquema y consultas transaccionales
cogs/                  Comandos Slash y panel Staff
halloween/             Puertas, scheduler, componentes, registro y textos
utils/                 Permisos, roles, cooldown y errores/logging
tests/                 Pruebas unitarias y de integración PostgreSQL
tools/package.py       ZIP de despliegue sin credenciales ni dependencias locales
tools/verify_postgres.py PostgreSQL temporal de pruebas para Windows
assets/README.md        Instrucciones de recursos gráficos
squarecloud.app        Entrada de despliegue: bot.py
.env.example           Nombres de variables, sin credenciales
```

## Instalación local

En PowerShell, desde la raíz:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# Completa .env únicamente en tu equipo.
.\.venv\Scripts\python.exe bot.py
```

En Linux/macOS, utiliza `.venv/bin/python` en lugar de `.venv\Scripts\python.exe`.
Con Python y las dependencias del entorno activo, el comando principal es:

```text
python bot.py
```

`.env` es opcional: las variables del sistema tienen prioridad y producción puede
arrancar sin ese archivo. Si falta `DISCORD_TOKEN` o `DATABASE_URL`, el inicio se
detiene con el nombre de la variable faltante. No se registran sus valores.

## Discord Developer Portal y permisos

1. Crea una aplicación en [Discord Developer Portal](https://discord.com/developers/applications)
   y configura su bot. Guarda su token únicamente en el entorno.
2. Crea la invitación con scopes `bot` y `applications.commands`.
3. Concede `View Channels`, `Send Messages`, `Embed Links`, `Read Message History`
   y `Manage Roles`. Los usuarios necesitan poder utilizar Application Commands.
   No se requiere `Administrator`.
4. Coloca el rol del bot **por encima del rol participante `1556139539502989404`**.
   El rol participante debe ser un rol normal asignable, no administrado por otra
   integración. Revisa también los permisos específicos de cada canal.
5. No actives Message Content ni Presence Intent. Este bot solo activa Guilds;
   Discord incluye los roles del usuario en la interacción del servidor. Si hace
   falta recuperar un miembro, se utiliza `fetch_member` por REST.

Los comandos se sincronizan al iniciar. Para pruebas en un servidor, configura
`COMMAND_GUILD_ID` con su ID: la sincronización en ese servidor evita esperar la
propagación global. Para producción puedes dejarlo vacío. Si antes creaste copias
de prueba de los comandos, elimina esas copias de servidor al pasar a globales.

Referencias: [interacciones discord.py](https://discordpy.readthedocs.io/en/stable/interactions/api.html)
y [Views persistentes del proyecto discord.py](https://github.com/Rapptz/discord.py/blob/master/examples/views/persistent.py).

## Variables de entorno

| Variable | Uso |
| --- | --- |
| `DISCORD_TOKEN` | Token del bot; obligatorio |
| `DATABASE_URL` | URL de conexión PostgreSQL; obligatoria |
| `ES_DOOR_CLOSED_GIF` | Puerta cerrada ES |
| `ES_DOOR_WAITING_GIF` | Animación de espera ES |
| `ES_DOOR_CANDY_WIN_GIF` | Ganar dulces ES |
| `ES_DOOR_CANDY_LOSE_GIF` | Perder dulces ES |
| `ES_DOOR_TIMEOUT` | Imagen de puerta vencida ES |
| `BR_DOOR_CLOSED_GIF` | Puerta cerrada BR |
| `BR_DOOR_WAITING_GIF` | Animación de espera BR |
| `BR_DOOR_CANDY_WIN_GIF` | Ganhar doces BR |
| `BR_DOOR_CANDY_LOSE_GIF` | Perder doces BR |
| `BR_DOOR_TIMEOUT` | Imagen de puerta vencida BR |
| `DATABASE_CA_FILE` | Opcional: ruta al certificado CA de Aiven |
| `DATABASE_CA_PEM` | Opcional: contenido PEM de la CA, admite saltos `\n` |
| `COMMAND_GUILD_ID` | Opcional: servidor de sincronización para desarrollo |
| `LOG_LEVEL` | Opcional: `INFO` por defecto |

Las imágenes ya tienen valores predeterminados incluidos en `config/settings.py`
para ambos idiomas:

- Puerta cerrada y espera: `https://pub-a09b3609b6b34dfab5c7aa7742cd1a8a.r2.dev/Puerta%201.gif`.
- Ganar ES y BR: `https://pub-a09b3609b6b34dfab5c7aa7742cd1a8a.r2.dev/DulcesGIF.gif`.
- Perder ES y BR: `https://pub-a09b3609b6b34dfab5c7aa7742cd1a8a.r2.dev/RobaGIF.gif`.
- Puerta vencida ES y BR: `https://pub-a09b3609b6b34dfab5c7aa7742cd1a8a.r2.dev/Vencida.png`.

No necesitas configurar las diez variables para mostrar imágenes. Si una variable
está ausente o vacía, se utiliza el valor predeterminado; una URL HTTPS en esa
variable sustituye únicamente la fase e idioma correspondientes. Reinicia el bot
después de cambiar las variables.

Compatibilidad: `ES_DOOR_RESULT_GIF` y `BR_DOOR_RESULT_GIF` siguen aceptándose como
respaldo para ganar cuando el nuevo nombre está ausente o vacío. El nuevo nombre
no vacío tiene prioridad. Renombra las variables antiguas al actualizar Square.

## Aiven PostgreSQL y SSL

En Aiven, crea o utiliza PostgreSQL y copia la URI de conexión desde el resumen del
servicio. Configúrala como `DATABASE_URL`; no la guardes en código, commits o README.

Formato ilustrativo, con valores ficticios:

```text
postgresql://USUARIO:CONTRASENA@HOST:PUERTO/BASE?sslmode=require
```

El pool utiliza TLS obligatorio. Se admiten `require`, `verify-ca` y `verify-full`;
se rechazan modos que permitan conexión sin cifrado. `sslmode=require` cifra la
conexión, pero no verifica la identidad del servidor. Para producción, descarga la
CA del proyecto Aiven y configura `DATABASE_CA_PEM` o `DATABASE_CA_FILE`. Con una CA
explícita, el bot verifica **certificado y nombre del host**, incluso si la URL
original incluye `sslmode=require`. No uses una dirección IP distinta del nombre
del certificado. Alternativamente, asyncpg admite `sslmode=verify-full` y
`sslrootcert` en la URL.

La única variable de conexión es `DATABASE_URL`; las dos variables CA son opciones
de verificación TLS, no conexiones separadas. Si tienes caracteres especiales en
las credenciales, usa la URI de Aiven correctamente codificada.

Las tablas e índices se crean al iniciar. El usuario PostgreSQL debe tener permisos
de conexión y de creación/lectura/escritura en el esquema del bot. Utiliza una base
destinada a este proyecto y la conexión directa de PostgreSQL; el scheduler usa un
advisory lock de sesión, que no es compatible con un pooler en modo transacción.

Referencia: [TLS de Aiven](https://aiven.io/docs/platform/concepts/tls-ssl-certificates)
y [conexiones/pools asyncpg](https://magicstack.github.io/asyncpg/current/api/index.html).

## Registro Halloween

El Staff ejecuta `/abrir_registro_halloween` en el canal elegido. Publica un Embed
público con el título `🎃 Evento Halloween Supersus SA Oficial 🎃`, sin descripción
ni footer, y el botón verde **Entrar**. El botón usa un ID estable y `timeout=None`;
se registra al iniciar y sigue funcionando tras un reinicio.

Para obtener el rol participante `1556139539502989404`, el usuario debe tener al
menos uno de estos roles verificados:

- `1527103455313793136`
- `1409401827065204786`

Si ya tiene el rol participante, se informa sin volver a asignarlo. Si no está
verificado, no se le asigna. Las respuestas son privadas. La asignación comprueba
Manage Roles y la jerarquía y utiliza el endpoint idempotente de Discord.

Canales indicados en los mensajes de usuarios sin registro:

- ES: `1486041460200571140`
- BR: `1415720295628537867`

Publica el registro en esos canales o revisa las constantes si cambia la organización.
Los IDs se encuentran centralizados en `config/constants.py`.

## Staff y comandos

La autorización se verifica mediante un check compartido. Están autorizados los
miembros que tengan **al menos uno** de estos Discord Role IDs de Staff/gerencia:

- `1524778858329411774`
- `1526645598961537064`
- `1464644504903614629`

Los tres IDs son roles y se centralizan en `STAFF_ROLE_IDS`, dentro de
`config/constants.py`. No existe una lista de usuarios autorizados por ID.
El check de comandos, botones,
selectores y envío de Modals utiliza la misma autorización. Si se retira el rol,
las siguientes interacciones dejan de estar autorizadas, salvo que conserve otro
rol de Staff permitido. El panel sigue reservado al Staff que lo abrió.
No se conceden excepciones por tener Administrator o un rol Staff diferente.

| Comando | Función | Respuesta |
| --- | --- | --- |
| `/abrir_registro_halloween` | Publicar registro permanente, solo Staff | Pública |
| `/doces` | Top BR de hasta 15 usuarios | Pública |
| `/dulces` | Top ES de hasta 15 usuarios | Pública |
| `/config_doces` | Panel Staff con Español/Português | Privada |
| `/ativar_doces` | Activar idiomas con Canal y CD completos | Pública |
| `/desativar_doces` | Desactivar ambos y cancelar apariciones pendientes | Pública |
| `/resetar_doces user idioma` | Poner saldo a cero | Privada |
| `/adicionar_doces user quantidade idioma` | Agregar cantidad positiva | Pública |
| `/tirar_doces user quantidade idioma` | Restar sin bajar de cero | Pública |
| `/porta_de_teste canal idioma recompensa_real` | Puerta de prueba aislada | Solo puerta pública; sin confirmación privada ni enlace al mensaje |

Los cambios manuales, activaciones y ajustes quedan registrados en `admin_logs`,
incluido el ID del responsable. Las cantidades se modifican atómicamente.

Rankings: orden descendente por dulces; los empates se ordenan por User ID ascendente.
Las cantidades del ranking, premios y robos usan `<:doce:1556451862969065512>` como unidad
en ES y BR; por ejemplo, `<@usuario>: 4 <:doce:1556451862969065512>`.
Se omiten saldos cero. Cada comando tiene cooldown independiente de 30 segundos por
usuario y servidor, con el tiempo restante real y respuesta privada al bloquear.
Este cooldown breve se guarda en memoria y se reinicia al reiniciar el bot; los
saldos y los timers del evento sí permanecen en PostgreSQL.

## Configurar ES y BR

1. Ejecuta `/config_doces` con una cuenta Staff.
2. Selecciona **🇪🇸 Español** o **🇧🇷 Português**.
3. En **Canal**, elige un canal de texto con el selector nativo de Discord.
4. En **CD puertas / CD das portas**, introduce mínimo y máximo, en minutos enteros
   positivos, con máximo mayor o igual al mínimo. No hay intervalo predefinido:
   debes configurar ambos valores.
5. En **Probabilidad / Probabilidade**, introduce **%ganar / %perder** o
   **%ganhar / %perder**. Son enteros de 0 a 100 que deben sumar 100. Por defecto:
   100% ganar y 0% perder, independientemente para ES y BR.
6. **Estado** consulta PostgreSQL y muestra estado activo, canal, CD mínimo/máximo,
   próxima aparición y minutos reales desde la última puerta. No altera ajustes.
   También muestra las probabilidades guardadas.
7. Ejecuta `/ativar_doces`. Solo se activan idiomas completos; se informa cuáles faltan.

El panel tiene 10 minutos de duración y solo lo puede operar el Staff que lo abrió.
Al guardar Canal, CD o Probabilidad, el mismo embed vuelve automáticamente al menú
principal con los botones Español y Português. Los valores inválidos o un error
al guardar mantienen la pantalla de configuración para volver a intentarlo.
Si caduca, vuelve a usar el comando. Los botones públicos de registro y puerta
permanecen persistentes.

Cada idioma conserva su canal, rango, próxima aparición y ranking. La primera puerta
se programa con un intervalo aleatorio del rango configurado. Tras completar una
puerta, se consulta el rango actual y se programa la siguiente. Un cambio de CD no
recalcula un timer ya programado; se aplica en la siguiente programación. Un cambio
de canal se aplica al preparar la siguiente puerta. Una puerta ya publicada sigue
en su canal original.

## Puertas y recompensas

1. Se crea un drop en PostgreSQL, se sortea una sola victoria o derrota según la
   probabilidad del idioma y se guarda el resultado para ambos participantes.
   Se envía un mensaje con la puerta cerrada y
   **Abrir** verde.
2. Se revisa primero el rol participante. Los usuarios sin él reciben el Embed
   privado de registro, no consumen cupo y no modifican el ranking.
3. Se aceptan como máximo dos usuarios distintos. En una victoria, cada aceptación sortea
   1–5 dulces. En una derrota, cada usuario pierde una cantidad aleatoria independiente
   de 2–5 dulces, limitada por su saldo: nunca baja de cero. Participación y cambio
   de saldo se guardan en una misma transacción, sin esperar al segundo usuario.
4. La puerta recibe hasta dos participantes durante 6 segundos desde su publicación.
   El primer clic mantiene la puerta abierta. Al entrar el segundo, o al terminar
   los 6 segundos con un participante, se edita **el mismo mensaje** a «Esperando recompensas»
   con su GIF y el botón Abrir rojo desactivado. Sin participantes, la puerta vence.
5. A los 5 segundos desde iniciar la fase de espera, se vuelve a editar **ese mismo Message ID** para mostrar
   participantes y el GIF de ganar o perder, eliminando el botón. El embed de derrota
   muestra el descuento real de cada usuario; con saldo cero muestra 0. Ambos resultados
   conservan el footer del top correspondiente al idioma. El resultado se publica
   con uno o dos participantes; no espera indefinidamente al segundo. Se programa
   el siguiente drop.

El clic aceptado se confirma silenciosamente: no se envía un resultado ni una
confirmación de recompensa efímera. Puerta cerrada, espera y resultado se muestran
editando el mismo embed público con su GIF correspondiente. Los avisos de falta de
registro, clic duplicado, puerta cerrada o vencida sí son privados.

Un cambio de probabilidades afecta a las nuevas puertas. Las ya creadas conservan
su resultado, incluso tras reinicios. El top consulta los saldos confirmados en
PostgreSQL y refleja premios y descuentos en la siguiente consulta.

Desde su publicación, una puerta admite participantes durante **6 segundos**.
Si nadie registrado abre a tiempo, vence sin premios ni descuentos y se programa
la siguiente aparición automática. El botón pasa a rojo y solo responde en privado
`Puerta Vencida, espera la proxima...` (ES) o `Porta expirou, aguarde pela proxima...`
(BR). Discord no envía interacciones de botones deshabilitados: este botón conserva
el clic exclusivamente para informar del vencimiento y no admite participantes.
El mensaje vencido se elimina **10 segundos después de mostrar el estado vencido**.

Con un participante, la puerta sigue abierta hasta completar los 6 segundos originales.
Con dos, inicia la fase de espera inmediatamente. Durante esa fase, Abrir está
desactivado y se rechazan clics antiguos antes de modificar saldos. La espera de
recompensas dura 5 segundos y se recupera tras reinicios. El resultado final, tanto al ganar
como al perder, se elimina **20 segundos después de publicarse**. Los plazos y el
estado del borrado se guardan en PostgreSQL y se recuperan al reiniciar, conservando
las puntuaciones. Los borrados pendientes de mensajes ya finalizados se recuperan
sin volver a repartir ni descontar dulces.

Desactivar cancela timers y puertas aún no publicadas; las puertas publicadas
mantienen estas reglas, pero no programan otra mientras el idioma esté desactivado.
El campo Última Puerta corresponde a la fecha
de creación del último drop automático publicado, no a pruebas ni consultas de Estado.

Las puertas de prueba utilizan el mismo servicio, componentes y transacciones. Por
defecto `recompensa_real=False`: simulan resultados sin tocar saldos. Con `True`
se aplican premios o descuentos reales. En ambos casos se exige el rol participante. Nunca cambian
el timer ni la fecha de última puerta del sistema automático.

## Concurrencia, recuperación y errores

- Lock local por puerta y `SELECT FOR UPDATE` para ordenar claims.
- La recepción de participantes conserva el plazo de 6 segundos de publicación.
  Al cerrar cupos se inicia una espera de 5 segundos con Abrir desactivado.
  La resolución usa una tarea separada de los chequeos de puertas abiertas.
- La actualización del esquema recupera puertas de la versión anterior que quedaron
  abiertas con un solo participante; conserva las puntuaciones ya confirmadas.
- Unicidad `(drop_id,user_id)` y `(drop_id,slot)`; PostgreSQL solo admite slots 1–2.
- Ganador, premio y cambio de saldo se confirman o revierten juntos.
- Índice único parcial: una sola puerta automática viva por servidor/idioma.
- Publicación y desactivación comparten bloqueos para cancelar envíos pendientes.
- Un advisory lock de sesión permite un único scheduler activo por base de datos.
  Utiliza una sola réplica del bot en producción. Un proceso extra espera y no publica.
- Si se pierde conexión a PostgreSQL, se pausan trabajos y se intenta recuperar la
  conexión cada 10 segundos. El pool reemplaza conexiones cerradas. No se reejecutan
  automáticamente mutaciones ambiguas: un usuario puede reintentar el claim y la
  unicidad impide volver a cobrarlo.
- Una puerta abierta conserva sus ganadores; una puerta en proceso vuelve a editar
  el mensaje y termina usando los premios guardados, sin sortearlos ni pagarlos otra vez.
- Si Discord aceptó el envío pero todavía no se guardó el ID, se busca su custom_id
  en el historial del canal antes de enviar. Por eso Read Message History es necesario.
  La publicación en Discord y la escritura PostgreSQL no constituyen una transacción
  distribuida; la recuperación depende de que el historial original siga accesible.
- Los drops finalizados nunca se vuelven a activar. Botones antiguos se rechazan con
  el estado real de PostgreSQL, aunque Discord todavía muestre un componente.
- Un mensaje eliminado cancela ese drop y conserva premios ya confirmados. Si el
  canal desaparece o faltan permisos, se suspende el idioma para evitar errores
  repetidos; corrige el problema y vuelve a activar.
- Errores transitorios se registran con traceback y reintentos espaciados. Tokens,
  URLs de conexión y contraseñas se redactan en logs.
- El scheduler inspecciona vencimientos cada 5 segundos; el rango se respeta con ese
  pequeño margen de ejecución. ES y BR trabajan en tareas separadas.

## Logs en Square Cloud

Con `LOG_LEVEL=INFO`, el arranque muestra pasos breves con ✅, sin repetir la fecha,
el nivel y el nombre de cada módulo; Square Cloud ya añade su propia fecha/hora.
Se informa de PostgreSQL y esquema, botones persistentes, módulos, comandos, GIFs,
Discord, servidores y scheduler. Después se muestran Canal, CD, estado y próxima
aparición ES/BR, junto con la comprobación del permiso y jerarquía del rol Halloween.

El mensaje `✅ Blackjack Conectado - 100% del inicio verificado` solo aparece después
de un ciclo correcto del scheduler y de superar las comprobaciones de configuración.
Describe esos controles de inicio, no garantiza que todas las operaciones futuras
estén libres de errores. Si hay cero servidores, faltan Canal/CD o permisos, el
resumen indica `Blackjack Conectado - configuración pendiente` y explica qué falta.
Un idioma configurado e inactivo se informa como Inactivo; no se activa por mostrar logs.

Se conservan advertencias, errores, tracebacks y la redacción de secretos. Se omiten
los mensajes rutinarios de conexión internos de discord.py y las advertencias sobre
PyNaCl/davey: este proyecto no utiliza funciones de voz. Para diagnóstico más detallado,
establece `LOG_LEVEL=DEBUG` y reinicia. Las reconexiones y cambios de servidor producen
una nueva comprobación; el resumen no se repite en cada ciclo del scheduler.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m compileall .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

Sin `TEST_DATABASE_URL`, las pruebas PostgreSQL se omiten. Para ejecutarlas, utiliza
una base de pruebas en la que se permita crear y eliminar esquemas:

```powershell
$env:TEST_DATABASE_URL='postgresql://USUARIO:CONTRASENA@HOST:PUERTO/BASE_PRUEBAS?sslmode=require'
.\.venv\Scripts\python.exe -m pytest -q
```

Cada prueba crea un esquema `test_halloween_<uuid>` y lo elimina al terminar. No uses
una base de producción para estas pruebas. En Windows también puedes ejecutar:

```powershell
.\.venv\Scripts\python.exe tools\verify_postgres.py
```

Ese auxiliar descarga binarios PostgreSQL del proveedor EDB a `.test-postgres/`,
crea una instancia de prueba en `127.0.0.1` con puerto libre, ejecuta las pruebas y
detiene la instancia. No instala un servicio del sistema. La autenticación local
`trust` se limita a esta instancia temporal. El directorio está ignorado por Git
y no se incluye en el ZIP de despliegue.

Se verifican recompensas, cooldown, roles, validaciones, Cogs y componentes,
simultaneidad de 40 claims, duplicados, constraints, rollback, independencia ES/BR,
timers, auditoría y recuperación de publicación/proceso sobre el mismo mensaje.
Las pruebas del flujo Discord usan dobles de mensajes: para confirmar permisos,
propagación de comandos y reproducción de GIFs hace falta una prueba final en tu
servidor con las variables reales de producción.

Resultados del desarrollo y límites de la validación: [VALIDATION.md](VALIDATION.md).

## GitHub

Sube los archivos fuente, README, requirements, tests y configuración de despliegue
a tu repositorio. `.gitignore` excluye `.env`, credenciales locales, cachés, entorno
virtual, archivos de certificados locales y PostgreSQL de pruebas. No subas
`.venv/`, `.test-postgres/` ni el ZIP como código fuente. Este proyecto no incluye
tokens, credenciales reales o un remoto GitHub preconfigurado.

## Square Cloud y despliegue

Se incluye `squarecloud.app`, usando el formato actual documentado:

```text
DISPLAY_NAME=Halloween Supersus SA
MAIN=bot.py
MEMORY=512
VERSION=recommended
```

La plataforma instala `requirements.txt` y ejecuta la entrada Python. Ajusta la RAM
según tu plan. Referencias oficiales: [Python en Square Cloud](https://squarecloud.app/en/runtimes/python)
y [despliegue de bots y variables](https://help.squarecloud.app/en-us/article/how-to-host-a-discord-bot-247-e2udcn/).

1. Crea el paquete limpio: `python tools/package.py`. Se genera
   `halloween-squarecloud.zip`, con `bot.py` en la raíz. No contiene `.env`, tests,
   PostgreSQL temporal, cachés, `.git` o dependencias locales.
2. Sube el ZIP en el panel de Square Cloud, o conecta el repositorio utilizando la
   opción disponible en tu cuenta. Mantén la entrada `bot.py` y `requirements.txt`.
3. Configura `DISCORD_TOKEN`, `DATABASE_URL` y la CA recomendada en las variables de
   la aplicación. No hace falta subir `.env` a producción.
4. Los GIFs ya están incluidos para las ocho combinaciones; si deseas sustituirlos, configura las
   variables correspondientes y reinicia la aplicación para leerlas.
5. Revisa logs de conexión PostgreSQL, Cogs, sincronización y scheduler.
6. Publica el registro, configura ES/BR y prueba primero una puerta simulada.
7. Prueba con dos participantes, un usuario no registrado y un tercer participante.
   Verifica los permisos reales y luego activa el evento.

## Recursos finales

Los GIFs proporcionados ya están integrados como valores predeterminados. Para
utilizar imágenes diferentes en el futuro, puedes sustituirlas individualmente:

```dotenv
ES_DOOR_CLOSED_GIF=
ES_DOOR_WAITING_GIF=
ES_DOOR_CANDY_WIN_GIF=
ES_DOOR_CANDY_LOSE_GIF=
ES_DOOR_TIMEOUT=
BR_DOOR_CLOSED_GIF=
BR_DOOR_WAITING_GIF=
BR_DOOR_CANDY_WIN_GIF=
BR_DOOR_CANDY_LOSE_GIF=
BR_DOOR_TIMEOUT=
```

Después de configurarlas, revisa las tres fases en ES y BR con `/porta_de_teste`.
Para probar una derrota, configura temporalmente 0% ganar / 100% perder en ese
idioma y crea una puerta de prueba con `recompensa_real=False`. Después restaura
las probabilidades deseadas. Al iniciar, el esquema se actualiza automáticamente
conservando puntuaciones y puertas existentes; estas últimas siguen siendo victorias.
Los tokens y credenciales se configuran en Square Cloud; no hace falta compartirlos
en el chat para completar el código.
