"""The box's own: the mailbox it sends through, its Google client, and the brand its pages and emails carry."""

from fastapi import APIRouter

from pinecall_runtime.accounts import schemas
from pinecall_runtime.accounts.auth import BrandDep, OutboxDep, PublicUrl, TheOperator
from pinecall_runtime.accounts.service import emails, google, mail
from pinecall_runtime.exceptions import Conflict, NotFound
from pinecall_runtime.kit.handles import TheHandles
from pinecall_runtime.platform import service as platform
from pinecall_runtime.postgres import Session

router = APIRouter()

NOTHING_STORED = "this box has no stored mail server: what it sends through, if anything, is PINECALL_SMTP_URL"
NOTHING_TO_TEST = "this box has no mail server: set one at PUT /v1/ops/mail, or set PINECALL_SMTP_URL"


# ── the box's mailbox ──


@router.get("/v1/ops/mail")
async def get_box_mail(
    _actor: TheOperator, handles: TheHandles, session: Session, outbox_: OutboxDep
) -> schemas.BoxMailRow:
    """The mailbox the box sends through, where it came from, and how its last email went."""
    return _box_mail_row(await mail.get_box_mailbox(session, handles.vault, outbox_.box_mailbox))


# Sends nothing: the test endpoint does, and a person watches it.
@router.put("/v1/ops/mail")
async def put_box_mail(
    body: schemas.PutMail, _actor: TheOperator, handles: TheHandles, session: Session, outbox_: OutboxDep
) -> schemas.BoxMailRow:
    """The box's mailbox, stored over the environment's; its emails go through it next."""
    mailbox = mail.Mailbox(
        body.host.strip(), body.port, body.security, body.username.strip(), body.password, body.sender.strip()
    )
    await mail.put_box_mailbox(session, handles.vault, mailbox)
    return _box_mail_row(await mail.get_box_mailbox(session, handles.vault, outbox_.box_mailbox))


@router.delete("/v1/ops/mail", status_code=204)
async def delete_box_mail(_actor: TheOperator, session: Session) -> None:
    """Forget the stored mailbox, back to the environment's; 404 when none was stored."""
    if not await mail.delete_box_mailbox(session):
        raise NotFound(NOTHING_STORED)


# The one box endpoint that waits on SMTP: a person is watching.
@router.post("/v1/ops/mail/test")
async def send_box_test_email(
    body: schemas.SendTestEmail, _actor: TheOperator, outbox_: OutboxDep, brand: BrandDep
) -> schemas.TestEmailSent:
    """One test email through the box's mailbox, waited for."""
    to = mail.address_of(body.to)
    if await outbox_.mailbox_for(None) is None:
        raise Conflict(NOTHING_TO_TEST)
    error = await outbox_.send(None, emails.test_email(to, brand))
    return schemas.TestEmailSent(sent=error is None, error=error)


# ── Google, for every org's people ──


def _google_row(client_id: str | None, base: str) -> schemas.BoxProvider:
    return schemas.BoxProvider(
        configured=client_id is not None, client_id=client_id, redirect_uri=f"{base}{google.CALLBACK}"
    )


@router.get("/v1/ops/signin")
async def get_box_signin(_actor: TheOperator, base: PublicUrl, session: Session) -> schemas.BoxSignIn:
    """Every provider the box offers every org's people, and the URI each registers; never a secret."""
    return schemas.BoxSignIn(google=_google_row(await google.client_id_of(session), base))


@router.put("/v1/ops/signin/google")
async def put_google_signin(
    body: schemas.PutSignIn, _actor: TheOperator, handles: TheHandles, base: PublicUrl, session: Session
) -> schemas.BoxProvider:
    """Keep the OAuth client the operator made at Google: "Continue with Google" shows on every page."""
    client = google.GoogleClient(client_id=body.client_id, client_secret=body.client_secret)
    await google.put_client(session, handles.vault, client)
    return _google_row(client.client_id.strip(), base)


@router.delete("/v1/ops/signin/google", status_code=204)
async def delete_google_signin(_actor: TheOperator, session: Session) -> None:
    """Forget the client: the button goes from every page."""
    if not await google.delete_client(session):
        raise NotFound("this box keeps no Google client")


# ── the brand ──


@router.get("/v1/ops/brand")
async def get_brand(_actor: TheOperator, brand: BrandDep) -> schemas.BrandRow:
    """What the box's emails and sign-in page are called and painted with."""
    return schemas.BrandRow(name=brand.name, logo_url=brand.logo_url, accent=brand.accent)


@router.put("/v1/ops/brand")
async def put_brand(body: schemas.PutBrand, _actor: TheOperator, session: Session, brand: BrandDep) -> schemas.BrandRow:
    """The brand changed field by field: one left out stays, an empty one goes to the default."""
    changed = platform.changed_brand(brand, name=body.name, logo_url=body.logo_url, accent=body.accent)
    await platform.put_brand(session, changed)
    return schemas.BrandRow(name=changed.name, logo_url=changed.logo_url, accent=changed.accent)


def _box_mail_row(kept: mail.MailboxStatus | None) -> schemas.BoxMailRow:
    """The box's mailbox as the endpoints send it; the password never."""
    if kept is None or kept.source == "org":
        return schemas.BoxMailRow.model_validate(
            {
                "configured": False,
                "source": None,
                "host": None,
                "port": None,
                "security": None,
                "username": None,
                "from": None,
                "verified_at": None,
                "last_error": None,
            }
        )
    return schemas.BoxMailRow.model_validate(
        {
            "configured": True,
            "source": kept.source,
            "host": kept.mailbox.host,
            "port": kept.mailbox.port,
            "security": kept.mailbox.security,
            "username": kept.mailbox.username,
            "from": kept.mailbox.sender,
            "verified_at": kept.verified_at,
            "last_error": kept.last_error,
        }
    )
