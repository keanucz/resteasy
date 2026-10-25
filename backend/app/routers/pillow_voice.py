"""How the pillow speaks to her, for the base laptop that speaks: the voice the family chose, its
speed, volume and tone, and her pronunciation dictionary. The laptop asks with the check-in token.
"""

from fastapi import APIRouter, Depends

from app.core.dependencies import ResidentDep, require_checkin_token
from app.schemas.voice import PillowVoice, VoiceStyle

router = APIRouter(prefix="/pillows/{pillow_id}/voice", tags=["voice"])


@router.get("", dependencies=[Depends(require_checkin_token)])
async def read_pillow_voice(resident: ResidentDep) -> PillowVoice:
    """The voice and style the family set for the pillow's resident."""
    style = VoiceStyle.of(resident)
    return PillowVoice(
        voice_id=resident["voice_id"],
        language=resident["language"],
        speed=style.speed,
        volume=style.volume,
        emotion=style.emotion,
        pronunciation_dict_id=resident["pronunciation_dict_id"],
    )
