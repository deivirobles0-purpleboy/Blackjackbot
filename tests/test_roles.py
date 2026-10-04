from config.constants import PARTICIPANT_ROLE_ID, VERIFIED_ROLE_IDS
from utils.roles import is_participant, is_verified


def test_participant_required():
    assert not is_participant([])
    assert not is_participant(VERIFIED_ROLE_IDS)
    assert is_participant([PARTICIPANT_ROLE_ID])


def test_either_verified_role_suffices():
    for role_id in VERIFIED_ROLE_IDS:
        assert is_verified([role_id])
    assert not is_verified([])
    assert not is_verified([PARTICIPANT_ROLE_ID, 123])
