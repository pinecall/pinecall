"""The visitor token: one web visitor of an org's env for a year, and nobody in another org or env."""

from runtime.actor import Scope
from runtime.enums import Env
from runtime.live.service import tokens

# Keys of HS256's own length at least: a shorter one is warned of, and the suite takes a warning as a failure.
LIVEKITS = "livekit's secret, long enough for HS256"
SIGNER = tokens.Signer(api_key="a key", secret=LIVEKITS, own="the gateway's own key, long enough for HS256")
HERE = Scope("an org", Env.production)


def test_a_visitor_token_names_its_visitor_in_its_own_org_and_env_alone() -> None:
    token = tokens.sign_visitor_token(SIGNER, "web_0123456789ab", HERE)
    assert tokens.read_visitor_token(SIGNER, token, HERE) == "web_0123456789ab"
    assert tokens.read_visitor_token(SIGNER, token, Scope("another org", Env.production)) is None
    assert tokens.read_visitor_token(SIGNER, token, Scope("an org", Env.sandbox)) is None


def test_no_other_token_and_no_other_key_names_a_visitor() -> None:
    other_key = tokens.Signer(api_key="a key", secret=LIVEKITS, own="another gateway's key, long enough for HS256")
    assert (
        tokens.read_visitor_token(other_key, tokens.sign_visitor_token(SIGNER, "web_0123456789ab", HERE), HERE) is None
    )
    assert tokens.read_visitor_token(SIGNER, tokens.sign_resume_token(SIGNER, "call_1"), HERE) is None
    assert tokens.read_resume_token(SIGNER, tokens.sign_visitor_token(SIGNER, "web_0123456789ab", HERE)) is None
    assert SIGNER.read(tokens.sign_visitor_token(SIGNER, "web_0123456789ab", HERE)) is None
    assert tokens.read_visitor_token(SIGNER, tokens.sign_visitor_token(SIGNER, "a person's id", HERE), HERE) is None
