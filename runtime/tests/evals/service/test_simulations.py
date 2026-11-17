"""How a simulated caller acts on the line a request names: its noise and its pause, else the persona's own."""

from runtime.evals.service.simulations import Scenario, Wanted, act_as_asked, as_placed, as_wanted
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


# What a call's facts keep is what the call is placed again with: the line it was on and the network
# its caller crossed with the rest.
def test_a_simulation_is_placed_again_on_the_line_and_the_network_it_was_placed_on() -> None:
    wanted = Wanted(
        agent="front",
        persona="in-a-hurry",
        turns=4,
        packet_loss=0.05,
        scenario=Scenario("I want Friday.", {"name": "Ana"}),
        by_phone=True,
        delay_ms=150.0,
        jitter_ms=40.0,
        rate_kbps=64.0,
    )
    assert as_wanted("front", "in-a-hurry", as_placed(wanted)) == wanted


def test_a_call_placed_before_it_kept_a_line_joins_the_room_on_a_clean_network() -> None:
    kept = {"spoken": True, "turns": 6, "packet_loss": 0.1}
    again = as_wanted("front", "in-a-hurry", kept)
    assert (again.by_phone, again.delay_ms, again.jitter_ms, again.rate_kbps) == (False, 0.0, 0.0, None)
    assert again.packet_loss == 0.1
