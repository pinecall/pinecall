"""The mail endpoints: an org's own mailbox and the box's, each read, replaced, forgotten and tried."""

from fastapi import APIRouter

from runtime.auth import TheOperator
from runtime.exceptions import NotFound
from runtime.handles import TheVault
from runtime.mail import schemas
from runtime.mail.auth import TeamKey, TheOutbox
from runtime.mail.service import mailboxes
from runtime.platform.auth import TheBrand
from runtime.postgres import Session

router = APIRouter()

NO_ORG_MAILBOX = "this org sends its emails through the box's own mail"
NOTHING_STORED = "this box has no stored mail server: what it sends through, if anything, is PINECALL_SMTP_URL"


@router.get("/v1/org/mail")
async def get_mail(actor: TeamKey, vault: TheVault, session: Session) -> schemas.MailRow:
    """The org's own mailbox, never its password, and how its last email went."""
    return schemas.MailRow.of_mailbox(await mailboxes.find_org_mailbox(session, vault, actor.org))


@router.put("/v1/org/mail")
async def put_mail(body: schemas.PutMail, actor: TeamKey, vault: TheVault, session: Session) -> schemas.MailRow:
    """Replace the org's own mailbox; its emails go through it from the next one."""
    await mailboxes.put_org_mailbox(session, vault, actor.org, mailboxes.Mailbox(**body.fields()))
    return schemas.MailRow.of_mailbox(await mailboxes.find_org_mailbox(session, vault, actor.org))


@router.delete("/v1/org/mail", status_code=204)
async def delete_mail(actor: TeamKey, session: Session) -> None:
    """Forget the org's own mailbox: its emails go through the box's again."""
    if not await mailboxes.delete_org_mailbox(session, actor.org):
        raise NotFound(NO_ORG_MAILBOX)


@router.post("/v1/org/mail/test")
async def send_test_email(
    body: schemas.SendTestEmail, actor: TeamKey, outbox: TheOutbox, brand: TheBrand
) -> schemas.TestEmailSent:
    """One test email, waited for: whether it went, and what the server said when not."""
    return schemas.TestEmailSent.of(await outbox.send_test(actor.org, body.to, brand))


@router.get("/v1/ops/mail")
async def get_box_mail(_actor: TheOperator, vault: TheVault, outbox: TheOutbox, session: Session) -> schemas.BoxMailRow:
    """The mailbox the box sends through, where it came from, and how its last email went."""
    return schemas.BoxMailRow.of_mailbox(await mailboxes.find_box_mailbox(session, vault, outbox.box_mailbox))


# Sends nothing: the test endpoint does, and a person watches it.
@router.put("/v1/ops/mail")
async def put_box_mail(
    body: schemas.PutMail, _actor: TheOperator, vault: TheVault, outbox: TheOutbox, session: Session
) -> schemas.BoxMailRow:
    """The box's mailbox, stored over the environment's; its emails go through it next."""
    await mailboxes.put_box_mailbox(session, vault, mailboxes.Mailbox(**body.fields()))
    return schemas.BoxMailRow.of_mailbox(await mailboxes.find_box_mailbox(session, vault, outbox.box_mailbox))


@router.delete("/v1/ops/mail", status_code=204)
async def delete_box_mail(_actor: TheOperator, session: Session) -> None:
    """Forget the stored mailbox, back to the environment's; 404 when none was stored."""
    if not await mailboxes.delete_box_mailbox(session):
        raise NotFound(NOTHING_STORED)


# The one box endpoint that waits on SMTP: a person is watching.
@router.post("/v1/ops/mail/test")
async def send_box_test_email(
    body: schemas.SendTestEmail, _actor: TheOperator, outbox: TheOutbox, brand: TheBrand
) -> schemas.TestEmailSent:
    """One test email through the box's mailbox, waited for."""
    return schemas.TestEmailSent.of(await outbox.send_test(None, body.to, brand))
