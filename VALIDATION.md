# Validación local — 4 de octubre de 2026

Entorno: Windows, Python 3.14.6, discord.py 2.7.1, asyncpg 0.31.0,
PostgreSQL 17.11 temporal en loopback. No se usaron credenciales de Discord ni Aiven.

## Resultados

- `python -m compileall .`: finalizó con código 0.
- `ruff check .`: sin errores.
- `pip check`: sin dependencias incompatibles.
- Suite completa con PostgreSQL tras integrar el regreso automático al menú: **121 pruebas aprobadas, ninguna omitida**.
- ZIP: integridad, entrada `bot.py`, configuración y sintaxis de los fuentes comprobadas.

La suite comprobó:

- Valores de recompensas y validación de cantidades/intervalos.
- Cooldown real e independiente por comando/usuario.
- Elegibilidad por rol y registro por roles verificados.
- Registro idempotente y rechazo controlado cuando faltan permisos de roles.
- Diez comandos Slash, opciones ES/BR, paneles, Modal y ChannelSelect.
- Views persistentes e IDs estables; botón de espera rojo desactivado.
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
- Dos puertas concurrentes no sobregiran el mismo saldo; claims duplicados y reinicios no vuelven a descontar.
- Rollback de pérdidas si falla guardar la participación; simulaciones mantienen saldos intactos.
- Migración repetible desde el esquema anterior conserva puntuaciones y puertas activas.
- Variables de entorno independientes por idioma/fase; valores vacíos usan el predeterminado.
- Tres fases ES y BR sobre el mismo Message ID con el GIF integrado y sin duplicar premios.
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
