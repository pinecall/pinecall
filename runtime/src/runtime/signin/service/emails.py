"""The emails of signing in: a forgotten password, a sign-up's code, and the two notes sent instead of one."""

from runtime.mail import service as mail
from runtime.platform import service as platform


def password_forgotten_email(to: str, link: mail.LinkDetails, brand: platform.Brand) -> mail.Email:
    """The email a forgotten password sends, which nobody may have asked for."""
    return mail.write_link_email(
        to,
        link,
        brand,
        mail.Wording(
            subject=f"Reset your {brand.name} password",
            title="Reset your password",
            said=(f"Somebody asked to reset the password for this address at {link.org}.",),
            label="Choose a password",
            unbidden=True,
        ),
    )


def account_exists_email(to: str, brand: platform.Brand) -> mail.Email:
    """Sent instead of a sign-up code when the address has an account already."""
    return mail.write_notice(
        to,
        brand,
        "You already have an account",
        (
            f"Somebody tried to sign up for {brand.name} with this address, which already has an "
            "account. To make another org, sign up again with the password you have; if you forgot "
            "it, reset it from the sign-in page."
        ),
    )


def invitation_waiting_email(to: str, brand: platform.Brand) -> mail.Email:
    """Sent instead of a sign-up code when the address was invited somewhere."""
    return mail.write_notice(
        to,
        brand,
        "You have an invitation waiting",
        (
            f"Somebody tried to sign up for {brand.name} with this address, which was invited to an "
            "org. Accept that invitation first, from the email it came in; then sign up with the "
            "password you chose there."
        ),
    )


# The code rides the preheader, never the subject: the outbox logs subjects.
def signup_code_email(to: str, code: str, person: str, brand: platform.Brand) -> mail.Email:
    """The email that carries a sign-up's six digits."""
    intro = f"Hi {person}, enter this code to finish setting up your {brand.name} account:"
    dies = "This code expires in 15 minutes."
    unbidden = f"If you did not create a {brand.name} account, ignore this email."
    footer = f"Sent by {brand.name}"
    body = (
        mail.heading("Confirm your email")
        + mail.paragraph(intro)
        + mail.code_block(code)
        + mail.small(dies)
        + mail.small(unbidden)
    )
    text = f"Confirm your email\n\n{intro}\n\n{code}\n\n{dies}\n\n{unbidden}\n\n{footer}"
    return mail.Email(
        to,
        f"Confirm your {brand.name} email",
        text,
        mail.frame(f"Your {brand.name} verification code is {code}", body, footer, brand),
    )
