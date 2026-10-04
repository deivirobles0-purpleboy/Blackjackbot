from dataclasses import dataclass

from config.constants import PARTICIPANT_ROLE_ID, REGISTRATION_CHANNEL_IDS
from halloween.models import Language


@dataclass(frozen=True)
class Texts:
    title: str
    closed: str
    waiting: str
    result: str
    footer: str
    candy: str
    not_registered: str
    duplicate: str
    unavailable: str
    accepted: str
    cooldown: str
    empty_ranking: str
    settings_title: str
    settings_description: str
    cd_button: str
    invalid_minutes: str


TEXTS = {
    Language.ES: Texts(
        title="Dulce o Truco ?",
        closed='Una puerta apareció... Apresúrate y presiona "Abrir" para reclamar tus recompensas.',
        waiting="Esperando recompensas...",
        result="Felicidades, obtuvieron...",
        footer="Consulta /dulces para revisar el Top!",
        candy="Dulces",
        not_registered=f"Debes de poseer el Rol: <@&{PARTICIPANT_ROLE_ID}> para participar..."
        f"Ingresa en <#{REGISTRATION_CHANNEL_IDS['ES']}> y registrate",
        duplicate="Ya participaste en esta puerta.",
        unavailable="Esta puerta ya no admite participantes o todavía se está preparando.",
        accepted="Tu participación quedó registrada. Recompensa: {amount} Dulces.",
        cooldown="Espera {seconds} segundos más para revisar el Top nuevamente!",
        empty_ranking="Todavía no hay dulces registrados.",
        settings_title="Ajustes Dulce o Truco",
        settings_description="Configura el Evento de dulces.",
        cd_button="CD puertas",
        invalid_minutes="Introduce minutos enteros positivos; máximo debe ser mayor o igual al mínimo.",
    ),
    Language.BR: Texts(
        title="Doces ou Travessuras ?",
        closed='Uma porta surgiu... Apresse-se e pressione "Abrir" para resgatar suas recompensas.',
        waiting="Esperando recompensas...",
        result="Parabéns, vocês conseguiram...",
        footer="Confira o /doces para consultar o top",
        candy="Doces",
        not_registered=f"Você precisa ter o cargo <@&{PARTICIPANT_ROLE_ID}> para participar... "
        f"Acesse ao <#{REGISTRATION_CHANNEL_IDS['BR']}> e registre-se.",
        duplicate="Você já participou desta porta.",
        unavailable="Esta porta não aceita mais participantes ou ainda está sendo preparada.",
        accepted="Sua participação foi registrada. Recompensa: {amount} Doces.",
        cooldown="Espera mais {seconds} segundos para conferir o Top!",
        empty_ranking="Ainda não há doces registrados.",
        settings_title="Configurações Doces ou Travessuras",
        settings_description="Configura o Evento de Doces.",
        cd_button="CD das portas",
        invalid_minutes="Informe minutos inteiros positivos; máximo deve ser maior ou igual ao mínimo.",
    ),
}
