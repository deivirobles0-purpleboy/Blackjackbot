# Validación local — 4 de octubre de 2026

Entorno: Windows, Python 3.14.6, discord.py 2.7.1, asyncpg 0.31.0,
PostgreSQL 17.11 temporal en loopback. No se usaron credenciales de Discord ni Aiven.

## Resultados

- `python -m compileall .`: finalizó con código 0.
- `ruff check .`: sin errores.
- `pip check`: sin dependencias incompatibles.
- Suite completa con PostgreSQL tras separar recepción de participantes y espera: **176 pruebas aprobadas, ninguna omitida**.
- Cambio posterior de unidades a `<:doce:1556451862969065512>`: **51 pruebas de componentes,
  flujo y recompensas aprobadas**; ranking ES/BR comprobado por separado con el emoji exacto.
- Activación y botón de puerta vencida: **28 pruebas de componentes y ciclo de vida aprobadas**.
  Respuesta de activación verificada con ambos idiomas, solo BR, solo ES y ninguno;
  el emoji check aparece únicamente junto a idiomas activados.
- Cambio de `/porta_de_teste`: **15 pruebas del comando y componentes aprobadas**, incluidas
  7 nuevas regresiones. Se elimina la respuesta temporal tras publicar, sin confirmación privada
  ni enlace; se conservan los errores de publicación para el manejador habitual.
- ZIP: integridad, entrada `bot.py`, configuración y sintaxis de los fuentes comprobadas.

La suite comprobó:

- Valores de recompensas y validación de cantidades/intervalos.
- Cooldown real e independiente por comando/usuario.
- Elegibilidad por rol y registro por roles verificados.
- Registro idempotente y rechazo controlado cuando faltan permisos de roles.
- Diez comandos Slash, opciones ES/BR, paneles, Modal y ChannelSelect.
- Views persistentes e IDs estables; botón activo al recibir participantes y rojo desactivado durante la espera.
- Imágenes separadas por idioma y fase mediante URLs ficticias en tests.
- GIFs integrados: Puerta para cierre/espera, Dulces para ganar y Roba para perder ES/BR.
- Variables CANDY_WIN/CANDY_LOSE independientes y compatibilidad con RESULT; el nombre nuevo tiene prioridad.
- Porcentajes enteros entre 0 y 100 que suman 100; valores predeterminados 100/0 por idioma.
- Límites exactos de sorteo (0%, 1%, 37%, 99%, 100%) y pérdidas de 2 a 5.
- Botones y modales localizados; validación y revalidación de permisos Staff antes de guardar.
- Guardar Canal, CD o Probabilidad vuelve al menú principal en el mismo mensaje privado ES/BR;
  datos inválidos y fallos al guardar conservan la pantalla para reintentar.
- Un resultado común persistido por puerta y descuentos individuales; nuevas probabilidades afectan nuevas puertas.
- Pérdidas limitadas al saldo disponible, incluido cero, y actualización inmediata del ranking.
- Cantidades de premios, robos (incluido cero) y ranking usan el emoji doce en ES y BR.
- Dos puertas concurrentes no sobregiran el mismo saldo; claims duplicados y reinicios no vuelven a descontar.
- Rollback de pérdidas si falla guardar la participación; simulaciones mantienen saldos intactos.
- Migración repetible desde el esquema anterior conserva puntuaciones y puertas activas.
- Plazo de 6 segundos desde la publicación para recibir participantes;
  clics tardíos no cambian puntuaciones aunque el temporizador aún no haya editado Discord.
- El primer clic conserva la puerta abierta hasta completar los 6 segundos originales; el segundo
  inicia la fase de espera inmediatamente. Con uno al vencer el plazo, también se resuelve.
  Usuarios no registrados no prolongan el tiempo. Carrera entre vencimiento y clics sin premios duplicados.
- Puerta vencida: aviso ES/BR, botón rojo desactivado con etiqueta «Que pena» y borrado a los 10 segundos.
  Clics enviados antes de la edición que llegan tarde siguen rechazándose en privado.
- Imagen Vencida.png integrada para puertas vencidas, con variables ES_DOOR_TIMEOUT y BR_DOOR_TIMEOUT;
  ausentes o vacías usan el valor predeterminado y las sustituciones son independientes por idioma.
- Resultado ganar/perder ES/BR: borrado a los 20 segundos, conservando saldos confirmados.
- Plazos persistidos y recuperación del vencimiento antes de editar Discord, así como del borrado final.
- Borrado idempotente; mensajes ya eliminados completan la limpieza y errores de permisos quedan pendientes.
- El scheduler recupera puertas abiertas y borrados pendientes; los trabajos se arman al publicar y finalizar.
- Variables de entorno independientes por idioma/fase; valores vacíos usan el predeterminado.
- Tres fases ES y BR sobre el mismo Message ID con el GIF integrado y sin duplicar premios.
- Clics del botón sin confirmaciones ni resultados efímeros para los dos participantes aceptados.
- Flujo completo por botón en ES/BR, ganar/perder y prueba real/simulada: un único envío público,
  mismo Message ID, GIF por fase y resultado final con título, descripción y footer correspondientes.
- Espera de 5 segundos desde cerrar cupos, con cuenta original conservada tras reinicios.
- Fase de espera con Abrir desactivado para uno o dos participantes; resultados sin botón.
- Descripción BR de pérdida: «Infelizmente, o Gatinho Múmia levou alguns dos teus doces com ele...».
- Regresión del bloqueo con un solo clic reproducida antes de corregir: la fase de espera no aparecía.
- Ocho pruebas completas con tareas de fondo y temporizadores reales (sin sustituir sleep ni avanzar
  fases manualmente): ES/BR, ganar/perder y uno/dos participantes. Espera observada al completar
  dos cupos o finalizar los 6 segundos; resultado observado 5 segundos después.
- En las ocho combinaciones, el borrado queda programado para 20 segundos después de la edición final,
  y el mensaje sigue presente al mostrarse el resultado. Un segundo clic antes de 6 segundos aún se admite ES/BR.
- Un chequeo OPEN que sigue ejecutándose no absorbe la tarea de resolución del primer clic.
- Cerrar cupos inicia el contador de recompensa; reintentos no lo reinician.
  Clics fuera del plazo o durante la espera se rechazan antes de modificar saldos.
- Reinicio durante la recepción de un participante conserva plazo y saldo, y resuelve al cerrar cupos.
- Migración de puertas antiguas abiertas con un solo participante y resolución tras reinicio sin volver a pagar.
- URL de Puerta comprobada previamente mediante GET parcial: HTTP 206, `image/gif` y firma GIF válida.
- 40 claims simultáneos: exactamente dos ganadores distintos y saldos coherentes.
- Repetición del mismo claim sin duplicar premio.
- Constraints de máximo dos slots, unicidad y saldos no negativos.
- Rollback completo si falla la escritura del premio.
- Rankings ES/BR independientes, top 15 y desempate estable.
- Auditoría de cambios manuales.
- Creación automática concurrente sin duplicar puerta.
- Reprogramación con el intervalo actual; activación idempotente.
- Puertas de prueba reales/simuladas sin modificar timers automáticos.
- Recuperación de una puerta en proceso y de envío previo al commit del Message ID.
- Dos ediciones sobre el mismo mensaje, sin volver a pagar premios.
- Cancelación de puertas pendientes y coordinación con publicación en curso.
- Reemplazo de conexiones PostgreSQL conservando claims y saldos.
- Un único propietario del advisory lock del scheduler.
- Cancelación de trabajos y espera entre reintentos tras errores.
- Resumen de inicio: no muestra éxito con cero servidores, configuración incompleta,
  permisos insuficientes o scheduler no disponible.
- Logs compactos con tracebacks y redacción de secretos; las advertencias de voz se
  omiten sin ocultar errores de Discord.
- Consulta de configuraciones para el resumen limitada a los servidores del bot,
  sin crear ni modificar registros.
- Los tres roles de gerencia autorizan individualmente todos los comandos Staff.
- Los IDs de usuario no conceden privilegios aunque coincidan con los IDs de roles.
- El panel revalida roles en cada interacción, mantiene su propietario y bloquea
  el acceso si pierde todos los roles permitidos.

discord.py produjo advertencias de deprecación sobre `asyncio.iscoroutinefunction`
en Python 3.14. No hubo fallos; la advertencia corresponde a una API que Python prevé
retirar en 3.16 y debe revisarse al actualizar a esa versión.
La inspección de etiquetas de TextInput en los tests también produjo advertencias
de deprecación de discord.py; los modales se crearon y procesaron correctamente.

## Validación pendiente en producción

El flujo Discord se probó con componentes reales de discord.py y dobles de canales,
mensajes e interacciones. Aún se necesita una prueba en el servidor para verificar
permisos y jerarquía reales, sincronización y acceso a canales. La conexión TLS a
la instancia Aiven del usuario se comprobará al configurar sus variables en Square
Cloud. Las ocho combinaciones utilizan tres URLs de GIFs integradas.
El acceso HTTP a los GIFs de ganar y perder queda pendiente de comprobar al desplegar.
La reproducción y el comportamiento visual en el
cliente real de Discord deben comprobarse al desplegar.

El proyecto incluye los recursos proporcionados y está preparado para configurar producción;
esta validación local no certifica un despliegue que todavía no se ha realizado.
