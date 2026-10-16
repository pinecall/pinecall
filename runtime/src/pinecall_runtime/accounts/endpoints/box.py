"""The box's own: the mailbox it sends through, box-wide sign-in, and the brand its pages and emails carry."""

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from pinecall_runtime.accounts import schemas
from pinecall_runtime.accounts.auth import BrandDep, OutboxDep, PublicUrl, TheOperator
from pinecall_runtime.accounts.service import emails, mail
from pinecall_runtime.exceptions import Conflict, NotFound, ServiceUnavailable
from pinecall_runtime.kit.handles import TheHandles
from pinecall_runtime.platform import service as platform
from pinecall_runtime.postgres import Session

router = APIRouter()

NOTHING_STORED = "this box has no stored mail server: what it sends through, if anything, is PINECALL_SMTP_URL"
NOTHING_TO_TEST = "this box has no mail server: set one at PUT /v1/ops/mail, or set PINECALL_SMTP_URL"
# Box-wide sign-in is not in this version: its endpoints stand, say so, and name the URI to register.
NO_BOX_WIDE = "box-wide sign-in is not in this version: each org signs in with its own identity provider"
GOOGLE_CALLBACK = "/v1/login/google/callback"


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


# ── sign-in across orgs ──


@router.get("/v1/ops/signin")
async def get_box_signin(_actor: TheOperator, base: PublicUrl) -> schemas.BoxSignIn:
    """Every provider the box could offer every org's people: none wired in this version."""
    return schemas.BoxSignIn(
        google=schemas.BoxProvider(configured=False, client_id=None, redirect_uri=f"{base}{GOOGLE_CALLBACK}")
    )


@router.put("/v1/ops/signin/google")
async def put_google_signin(_body: schemas.PutSignIn, _actor: TheOperator) -> schemas.BoxProvider:
    """Refused: box-wide Google sign-in is not in this version."""
    raise ServiceUnavailable(NO_BOX_WIDE)


@router.delete("/v1/ops/signin/google", status_code=204)
async def delete_google_signin(_actor: TheOperator) -> None:
    """Refused: box-wide Google sign-in is not in this version."""
    raise ServiceUnavailable(NO_BOX_WIDE)


@router.get("/v1/login/google")
async def google_sign_in() -> RedirectResponse:
    """Box-wide "Continue with Google", which this version does not have."""
    raise ServiceUnavailable(NO_BOX_WIDE)


@router.get(GOOGLE_CALLBACK)
async def google_callback() -> RedirectResponse:
    """Box-wide Google's callback, which this version does not have."""
    raise ServiceUnavailable(NO_BOX_WIDE)


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
