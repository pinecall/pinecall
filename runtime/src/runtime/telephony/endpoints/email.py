"""The org's email layout: the HTML its agents' replies are set in, read, written, forgotten, and tried on words."""

from fastapi import APIRouter

from runtime.exceptions import NotFound
from runtime.postgres import Session
from runtime.telephony.auth import NumbersKey
from runtime.telephony.schemas import email as schemas
from runtime.telephony.service import email_layout, email_reply

router = APIRouter()


@router.get("/v1/org/email/layout")
async def get_email_layout(actor: NumbersKey, session: Session) -> schemas.EmailLayoutRow:
    """The HTML the org's agents' emails are set in: its own, or the plain one while it wrote none."""
    return schemas.EmailLayoutRow.model_validate(await email_layout.layout_of(session, actor.org))


@router.put("/v1/org/email/layout")
async def put_email_layout(body: schemas.PutEmailLayout, actor: NumbersKey, session: Session) -> schemas.EmailLayoutRow:
    """Keep the org's layout: its agents' next emails are set in it."""
    kept = await email_layout.put_layout(session, actor.org, body.html, by=actor.asked_by)
    return schemas.EmailLayoutRow.model_validate(kept)


@router.delete("/v1/org/email/layout", status_code=204)
async def delete_email_layout(actor: NumbersKey, session: Session) -> None:
    """Forget the org's layout, back to the plain one."""
    if not await email_layout.delete_layout(session, actor.org):
        raise NotFound("the org has no layout of its own: its agents' emails are set in the plain one")


# Nothing is sent: what the contact would read, for the console's preview and `pinecall email layout preview`.
@router.post("/v1/org/email/layout/preview")
async def preview_email(body: schemas.PreviewEmail, actor: NumbersKey, session: Session) -> schemas.PreviewedEmail:
    """Words set in the layout as a reply would be: its subject, its HTML, its plain part."""
    kept = await email_layout.layout_of(session, actor.org)
    layout = email_layout.check_layout(body.html) if body.html else kept.html
    subject = email_reply.reply_subject(body.subject)
    return schemas.PreviewedEmail(
        subject=subject,
        html=email_layout.set_in(layout, body.text, subject=subject),
        text=email_layout.text_of(body.text),
    )
