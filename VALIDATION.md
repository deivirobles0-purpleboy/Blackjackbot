# Validación local — 4 de octubre de 2026

Entorno: Windows, Python 3.14.6, discord.py 2.7.1, asyncpg 0.31.0,
PostgreSQL 17.11 temporal en loopback. No se usaron credenciales de Discord ni Aiven.

## Resultados

- `python -m compileall .`: finalizó con código 0.
- `ruff check .`: sin errores.
- `pip check`: sin dependencias incompatibles.
- Suite completa con PostgreSQL: **48 pruebas aprobadas, ninguna omitida**.
- ZIP: integridad, entrada `bot.py`, configuración y sintaxis de los fuentes comprobadas.

La suite comprobó:

- Valores de recompensas y validación de cantidades/intervalos.
- Cooldown real e independiente por comando/usuario.
- Elegibilidad por rol y registro por roles verificados.
- Registro idempotente y rechazo controlado cuando faltan permisos de roles.
- Diez comandos Slash, opciones ES/BR, paneles, Modal y ChannelSelect.
- Views persistentes e IDs estables; botón de espera rojo desactivado.
- Imágenes separadas por idioma y fase mediante URLs ficticias en tests.
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

discord.py produjo dos advertencias de deprecación sobre `asyncio.iscoroutinefunction`
en Python 3.14. No hubo fallos; la advertencia corresponde a una API que Python prevé
retirar en 3.16 y debe revisarse al actualizar a esa versión.

## Validación pendiente en producción

El flujo Discord se probó con componentes reales de discord.py y dobles de canales,
mensajes e interacciones. Aún se necesita una prueba en el servidor para verificar
permisos y jerarquía reales, sincronización y acceso a canales. La conexión TLS a
la instancia Aiven del usuario se comprobará al configurar sus variables en Square
Cloud. Los seis GIFs definitivos están pendientes; hay que revisar accesibilidad
y reproducción de cada una de las tres fases en ES y BR cuando se proporcionen.

El proyecto está preparado para incorporar esos recursos y configurar producción;
esta validación local no certifica un despliegue que todavía no se ha realizado.
