"""How a simulated caller acts on the line a request names: its noise and its pause, else the persona's own."""

from runtime.evals.service.simulations import act_as_asked
from runtime.judging import service as judging


def test_the_line_is_the_requests_noise_or_else_the_personas_and_carries_how_it_acts() -> None:
    behavior = judging.Behavior(
        interrupts=0.4,
        pause_s=1.5,
        interferer_db=12.0,
        packet_loss=0.05,
        backchannels=0.3,
        speed=0.8,
        ambience="office",
    )
    own = act_as_asked(behavior, None, 0.0)
    assert (own.interferer_db, own.packet_loss, own.interrupts, own.pause_s) == (12.0, 0.05, 0.4, 1.5)
    # A preview wants a caller that answers at once: the request's pause stands over the persona's.
    assert act_as_asked(behavior, None, 0.0, pause_s=0.0).pause_s == 0.0
    assert (own.backchannels, own.speed, own.ambience) == (0.3, 0.8, "office")
    named = act_as_asked(behavior, 20.0, 0.1, "street")
    assert (named.interferer_db, named.packet_loss, named.interrupts) == (20.0, 0.1, 0.4)
    assert named.ambience == "street"
