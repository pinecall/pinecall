"""The billing endpoints: what a newborn org is given."""

from fastapi import APIRouter

from runtime.auth import TheOperator
from runtime.billing import schemas
from runtime.billing.service import admission
from runtime.postgres import Session

router = APIRouter()


@router.get("/v1/ops/admission")
async def get_admission(_actor: TheOperator, session: Session) -> schemas.Admission:
    """What a newborn org is given in each env; nothing limited on a box that never said."""
    kept = await admission.get_admission(session)
    return schemas.Admission.model_validate(admission.dump_admission(kept))


# Read at the moment an org is made: the orgs already made keep their quotas.
@router.put("/v1/ops/admission")
async def put_admission(body: schemas.Admission, _actor: TheOperator, session: Session) -> schemas.Admission:
    """What a newborn org is given, replaced whole."""
    await admission.put_admission(session, admission.load_admission(body.model_dump(mode="json")))
    return body
