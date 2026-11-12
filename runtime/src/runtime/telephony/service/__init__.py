"""Telephony's rules, one module per noun; what another domain uses is named here, and nothing else."""

from runtime.telephony.service.legs import (
    CALLER_NUMBER,
    LEG_PREFIX,
    NO_LEG,
    NO_TRUNK,
    Legs,
    caller_leg,
    dial_in,
    find_wrong_tone,
    is_a_phone,
    leg_to,
    send_on,
    send_tones,
)

__all__ = [
    "CALLER_NUMBER",
    "LEG_PREFIX",
    "NO_LEG",
    "NO_TRUNK",
    "Legs",
    "caller_leg",
    "dial_in",
    "find_wrong_tone",
    "is_a_phone",
    "leg_to",
    "send_on",
    "send_tones",
]
