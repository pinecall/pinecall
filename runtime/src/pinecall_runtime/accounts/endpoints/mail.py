"""The org's own mailbox: read, replaced, forgotten, and a test email through it."""

from fastapi import APIRouter, Request

from pinecall_runtime.accounts import schemas
from pinecall_runtime.accounts.auth import (
    BrandDep,
    OutboxDep,
    TeamKey,
)
from pinecall_runtime.accounts.service import emails, mail
from pinecall_runtime.exceptions import (
    Conflict,
    NotFound,
)
from pinecall_runtime.kit.handles import handles_of
from pinecall_runtime.postgres import Session

router = APIRouter()


@router.get("/v1/org/mail")
async def get_mail(actor: TeamKey, request: Request, session: Session) -> schemas.MailRow:
    """The org's own mailbox, never its password, and how its last email went."""
    return _mail_row(await mail.get_org_mailbox(session, handles_of(request).vault, actor.org))


@router.put("/v1/org/mail")
async def put_mail(body: schemas.PutMail, actor: TeamKey, request: Request, session: Session) -> schemas.MailRow:
    """Replace the org's own mailbox; its emails go through it from the next one."""
    mailbox = mail.Mailbox(
        body.host.strip(), body.port, body.security, body.username.strip(), body.password, body.sender.strip()
    )
    await mail.put_org_mailbox(session, handles_of(request).vault, actor.org, mailbox)
    return _mail_row(await mail.get_org_mailbox(session, handles_of(request).vault, actor.org))


@router.delete("/v1/org/mail", status_code=204)
async def drop_mail(actor: TeamKey, session: Session) -> None:
    """Forget the org's own mailbox: its emails go through the box's again."""
    if not await mail.delete_org_mailbox(session, actor.org):
        raise NotFound("this org sends its emails through the box's own mail")


@router.post("/v1/org/mail/test")
async def send_test_email(
    body: schemas.SendTestEmail, actor: TeamKey, outbox_: OutboxDep, brand: BrandDep
) -> schemas.TestEmailSent:
    """One test email, waited for: whether it went, and what the server said when not."""
    to = mail.address_of(body.to)
    if await outbox_.mailbox_for(actor.org) is None:
        raise Conflict(
            "neither this org nor this box has a mail server: set one at PUT /v1/org/mail, or "
            "PINECALL_SMTP_URL on the box"
        )
    error = await outbox_.send(actor.org, emails.test_email(to, brand))
    return schemas.TestEmailSent(sent=error is None, error=error)


def _mail_row(kept: mail.MailboxStatus | None) -> schemas.MailRow:
    if kept is None:
        return schemas.MailRow.model_validate(
            {
                "configured": False,
                "host": None,
                "port": None,
                "security": None,
                "username": None,
                "from": None,
                "verified_at": None,
                "last_error": None,
            }
        )
    return schemas.MailRow.model_validate(
        {
            "configured": True,
            "host": kept.mailbox.host,
            "port": kept.mailbox.port,
            "security": kept.mailbox.security,
            "username": kept.mailbox.username,
            "from": kept.mailbox.sender,
            "verified_at": kept.verified_at,
            "last_error": kept.last_error,
        }
    )
