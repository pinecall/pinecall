"""`box`: the vendor keys it lends, its Twilio account, what a newborn org is given, its test line, its alerts."""

import typer

from runtime.cli.box import admission, alerts, keys, numbers_account, test_line

app = typer.Typer(
    help="its keys, its Twilio, what a new org gets, its test line, where its alerts reach it", no_args_is_help=True
)
app.add_typer(keys.app, name="keys")
app.add_typer(numbers_account.app, name="numbers-account")
app.add_typer(admission.app, name="admission")
app.add_typer(test_line.app, name="test-line")
app.add_typer(alerts.app, name="alerts")
