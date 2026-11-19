"""The org's email layout: the HTML its agents' replies are set in, read, written, forgotten, and tried on words."""

from fastapi import APIRouter

from runtime.exceptions import NotFound, ValidationError
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
    """Keep how the org's emails are set: in its layout, or as text alone."""
    if body.text_only == (body.html is not None):
        raise ValidationError("say the layout's `html`, or `text_only` for emails with no HTML: one of the two")
    if body.html is None:
        kept = await email_layout.send_text_only(session, actor.org, by=actor.asked_by)
    else:
        kept = await email_layout.put_layout(session, actor.org, body.html, by=actor.asked_by)
    return schemas.EmailLayoutRow.model_validate(kept)


@router.delete("/v1/org/email/layout", status_code=204)
async def delete_email_layout(actor: NumbersKey, session: Session) -> None:
    """Forget how the org set its emails, back to the plain layout."""
    if not await email_layout.delete_layout(session, actor.org):
        raise NotFound("the org has no layout of its own: its agents' emails are set in the plain one")


# Nothing is sent: what the contact would read, for the console's preview and `pinecall email layout preview`.
@router.post("/v1/org/email/layout/preview")
async def preview_email(body: schemas.PreviewEmail, actor: NumbersKey, session: Session) -> schemas.PreviewedEmail:
    """Words set in the layout as a reply would be: its subject, its HTML, its plain part."""
    kept = await email_layout.layout_of(session, actor.org)
    tried = email_layout.check_layout(body.html) if body.html else email_layout.PLAIN if body.plain else None
    layout = kept.html if tried is None else tried
    text_only = kept.text_only and tried is None if body.text_only is None else body.text_only
    subject = email_reply.reply_subject(body.subject)
    return schemas.PreviewedEmail(
        subject=subject,
        html=None if text_only else email_layout.set_in(layout, body.text, subject=subject),
        text=email_layout.text_of(body.text),
    )
