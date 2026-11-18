"""Twilio's SMS webhooks over HTTP: a post at the number's own address is taken, at any other it is refused."""

import os
import secrets
from urllib.parse import urlencode

from runtime.kit.crypto import Vault
from runtime.telephony.service import sms
from tests.conftest import Gateway, needs_the_services

FORM = {"content-type": "application/x-www-form-urlencoded"}


@needs_the_services
async def test_a_post_at_the_numbers_own_address_is_taken_and_twilio_is_told_to_say_nothing(gateway: Gateway) -> None:
    """Nobody routed the number: the message is a line in the log, and Twilio is answered an empty reply."""
    number = f"+1555{secrets.randbelow(10**7):07d}"
    vault = Vault(os.environ["PINECALL_VAULT_KEY"])
    path = sms.sms_hook_url(vault, "", number)
    posted = {"To": number, "From": "+59899000001", "Body": "hola", "MessageSid": "SM1", "AccountSid": "AC1"}
    taken = await gateway.http.post(path, content=urlencode(posted), headers=FORM)
    assert (taken.status_code, taken.text) == (200, sms.NOTHING_TO_SAY)
    assert taken.headers["content-type"].startswith("text/xml")
    receipt = {"From": number, "To": "+59899000001", "MessageSid": "SM2", "MessageStatus": "delivered"}
    noted = await gateway.http.post(f"{path}/status", content=urlencode(receipt), headers=FORM)
    assert (noted.status_code, noted.text) == (200, sms.NOTHING_TO_SAY)


@needs_the_services
async def test_a_post_at_another_address_is_refused(gateway: Gateway) -> None:
    """The mark of another number, or a guess, opens nothing: a message and a receipt alike."""
    number, another = (f"+1555{secrets.randbelow(10**7):07d}" for _ in range(2))
    vault = Vault(os.environ["PINECALL_VAULT_KEY"])
    posted = {"To": number, "From": "+59899000001", "Body": "hola", "MessageSid": "SM1"}
    for path in (sms.sms_hook_url(vault, "", another), f"{sms.PATH}/a-guess"):
        refused = await gateway.http.post(path, content=urlencode(posted), headers=FORM)
        assert refused.status_code == 403, refused.text
        receipt = {"From": number, "To": "+59899000001", "MessageSid": "SM2", "MessageStatus": "sent"}
        refused = await gateway.http.post(f"{path}/status", content=urlencode(receipt), headers=FORM)
        assert refused.status_code == 403, refused.text
