from dataclasses import dataclass

from config.constants import CANDY_EMOJI, PARTICIPANT_ROLE_ID, REGISTRATION_CHANNEL_IDS
from halloween.models import Language


@dataclass(frozen=True)
class Texts:
    title: str
    closed: str
    waiting: str
    candy_win: str
    candy_lose: str
    lose_title: str
    footer: str
    candy: str
    not_registered: str
    duplicate: str
    unavailable: str
    cooldown: str
    empty_ranking: str
    settings_title: str
    settings_description: str
    cd_button: str
    invalid_minutes: str
    probability_button: str
    win_label: str
    lose_label: str
    invalid_probabilities: str
    probabilities_saved: str
    expired: str


TEXTS = {
    Language.ES: Texts(
        title="Dulce o Truco ?",
        closed='Una puerta apareció... Apresúrate y presiona "Abrir" para reclamar tus recompensas.',
        waiting="Esperando recompensas...",
        candy_win="Felicidades, obtuvieron...",
        candy_lose="Desafortunadamente el Gatico Momia se llevó algunos de tus dulces...",
        lose_title="Que mal! Truco...",
        footer="Consulta /dulces para revisar el Top!",
        candy=CANDY_EMOJI,
        not_registered=f"Debes de poseer el Rol: <@&{PARTICIPANT_ROLE_ID}> para participar..."
        f"Ingresa en <#{REGISTRATION_CHANNEL_IDS['ES']}> y registrate",
        duplicate="Ya participaste en esta puerta.",
        unavailable="Esta puerta ya no admite participantes o todavía se está preparando.",
        cooldown="Espera {seconds} segundos más para revisar el Top nuevamente!",
        empty_ranking="Todavía no hay dulces registrados.",
        settings_title="Ajustes Dulce o Truco",
        settings_description="Configura el Evento de dulces.",
        cd_button="CD puertas",
        invalid_minutes="Introduce minutos enteros positivos; máximo debe ser mayor o igual al mínimo.",
        probability_button="Probabilidad",
        win_label="%ganar",
        lose_label="%perder",
        invalid_probabilities="Introduce porcentajes enteros entre 0 y 100 que sumen 100%.",
        probabilities_saved="Probabilidad guardada: {win}% ganar / {lose}% perder. Se aplica a las nuevas puertas.",
        expired="Puerta Vencida, espera la proxima...",
    ),
    Language.BR: Texts(
        title="Doces ou Travessuras ?",
        closed='Uma porta surgiu... Apresse-se e pressione "Abrir" para resgatar suas recompensas.',
        waiting="Esperando recompensas...",
        candy_win="Parabéns, vocês conseguiram...",
        candy_lose="Infelizmente, o Gatinho Múmia levou alguns dos teus doces com ele...",
        lose_title="Foi mal! Travessuras...",
        footer="Confira o /doces para consultar o top",
        candy=CANDY_EMOJI,
        not_registered=f"Você precisa ter o cargo <@&{PARTICIPANT_ROLE_ID}> para participar... "
        f"Acesse ao <#{REGISTRATION_CHANNEL_IDS['BR']}> e registre-se.",
        duplicate="Você já participou desta porta.",
        unavailable="Esta porta não aceita mais participantes ou ainda está sendo preparada.",
        cooldown="Espera mais {seconds} segundos para conferir o Top!",
        empty_ranking="Ainda não há doces registrados.",
        settings_title="Configurações Doces ou Travessuras",
        settings_description="Configura o Evento de Doces.",
        cd_button="CD das portas",
        invalid_minutes="Informe minutos inteiros positivos; máximo deve ser maior ou igual ao mínimo.",
        probability_button="Probabilidade",
        win_label="%ganhar",
        lose_label="%perder",
        invalid_probabilities="Informe porcentagens inteiras entre 0 e 100 que somem 100%.",
        probabilities_saved="Probabilidade salva: {win}% ganhar / {lose}% perder. Aplica-se às novas portas.",
        expired="Porta expirou, aguarde pela proxima...",
    ),
}
