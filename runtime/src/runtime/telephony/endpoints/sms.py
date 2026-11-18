"""Twilio's SMS webhooks: a message written to one of the box's numbers, and where a reply stands."""

from fastapi import APIRouter, Response

from runtime.telephony.auth import TheSms, TheSmsReceipt
from runtime.telephony.service import sms
from runtime.whatsapp.auth import TheThreads

router = APIRouter()

XML = "text/xml"


# The address is the number's own, set on it at Twilio when the number was imported for SMS.
@router.post("/v1/sms/twilio/{mark}")
async def receive_sms(message: TheSms, threads: TheThreads) -> Response:
    """A message written to one of the box's numbers, onto its contact's conversation."""
    return Response(await sms.receive(threads, message), media_type=XML)


@router.post("/v1/sms/twilio/{mark}/status")
async def note_sms_status(receipt: TheSmsReceipt, threads: TheThreads) -> Response:
    """Where a reply sent by SMS stands, said on its contact's open conversation."""
    return Response(await sms.note(threads, receipt), media_type=XML)
