"""Telephony's rules, one module per noun; what another domain uses is named here, and nothing else."""

from runtime.telephony.service.accounts import email_account_of, list_own_meta_apps, meta_token_for, twilio_account_of
from runtime.telephony.service.carrier import SipNames
from runtime.telephony.service.email_account import EmailAccount
from runtime.telephony.service.email_box import read_new
from runtime.telephony.service.email_layout import Layout, layout_of
from runtime.telephony.service.email_message import read_email
from runtime.telephony.service.email_reply import compose_reply, send_reply
from runtime.telephony.service.hand_over import hand_on, unbridge
from runtime.telephony.service.inboxes import lease_inbox, list_routed_mailboxes, move_inbox
from runtime.telephony.service.legs import (
    CALLER_NUMBER,
    LEG_PREFIX,
    NO_LEG,
    NO_TRUNK,
    Arrival,
    Legs,
    Trunk,
    arrival_of,
    caller_leg,
    dial_in,
    end_reason_of,
    find_wrong_tone,
    is_a_phone,
    leg_to,
    outbound_leg,
    send_on,
    send_tones,
    sip_config,
)
from runtime.telephony.service.numbers import get_number, release_numbers_of
from runtime.telephony.service.outbound import get_carrier_for_number, list_phone_routes
from runtime.telephony.service.routes import (
    count_managed,
    find_route_at,
    list_answered_routes,
    list_routes,
    move_routes_with_agent,
    note_call,
)
from runtime.telephony.service.simulated_rings import (
    RINGS_FROM,
    callers_room,
    check_simulated_ring,
    hang_up_simulated_caller,
    ring_simulated_caller,
)
from runtime.telephony.service.sms import read_sms_media, send_sms, sms_account_of, sms_status_url
from runtime.telephony.service.test_line import find_test_line
from runtime.telephony.service.twilio import TwilioAccount

__all__ = [
    "CALLER_NUMBER",
    "LEG_PREFIX",
    "NO_LEG",
    "NO_TRUNK",
    "RINGS_FROM",
    "Arrival",
    "EmailAccount",
    "Layout",
    "Legs",
    "SipNames",
    "Trunk",
    "TwilioAccount",
    "arrival_of",
    "caller_leg",
    "callers_room",
    "check_simulated_ring",
    "compose_reply",
    "count_managed",
    "dial_in",
    "email_account_of",
    "end_reason_of",
    "find_route_at",
    "find_test_line",
    "find_wrong_tone",
    "get_carrier_for_number",
    "get_number",
    "hand_on",
    "hang_up_simulated_caller",
    "is_a_phone",
    "layout_of",
    "lease_inbox",
    "leg_to",
    "list_answered_routes",
    "list_own_meta_apps",
    "list_phone_routes",
    "list_routed_mailboxes",
    "list_routes",
    "meta_token_for",
    "move_inbox",
    "move_routes_with_agent",
    "note_call",
    "outbound_leg",
    "read_email",
    "read_new",
    "read_sms_media",
    "release_numbers_of",
    "ring_simulated_caller",
    "send_on",
    "send_reply",
    "send_sms",
    "send_tones",
    "sip_config",
    "sms_account_of",
    "sms_status_url",
    "twilio_account_of",
    "unbridge",
]
