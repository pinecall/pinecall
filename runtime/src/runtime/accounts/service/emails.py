"""The emails of an org's people: the invitation, and the reset an admin sends."""

from runtime.mail import service as mail
from runtime.platform import service as platform

# The console's page that opens a link's token: where a person chooses their password.
CARD = "/invitations/{token}"


def card_link(base: str, token: str) -> str:
    """The console's card for a token, at the name this gateway answers to."""
    return f"{base.rstrip('/')}{CARD.format(token=token)}"


def invitation_email(to: str, link: mail.LinkDetails, brand: platform.Brand) -> mail.Email:
    """The email that invites a person into an org."""
    return mail.write_link_email(
        to,
        link,
        brand,
        mail.Wording(
            subject=f"You're invited to {link.org} on {brand.name}",
            title="Join your team",
            said=(
                f"{link.by} has invited you to join {link.org} on {brand.name}.",
                "Choose a password and you are in.",
            ),
            label="Accept the invitation",
        ),
    )


def reset_email(to: str, link: mail.LinkDetails, brand: platform.Brand) -> mail.Email:
    """The email an admin's reset of a member's password sends."""
    return mail.write_link_email(
        to,
        link,
        brand,
        mail.Wording(
            subject=f"Reset your {brand.name} password",
            title="Set a new password",
            said=(f"{link.by} has reset your password for {link.org}.", "Choose a new one to sign in again."),
            label="Choose a password",
        ),
    )
