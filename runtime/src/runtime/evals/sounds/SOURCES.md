# The sounds a simulated caller's room is made of

Files the harness plays behind a simulated caller (`service/ambience.py`), shipped in the wheel.
Each is the same every run.

## `television.ogg`

One minute of a television as a caller's phone hears it from the couch: a real newscast played by
a small speaker in a living room, 2.14 m from the microphone. Ogg Opus, mono, 48 kHz.

It is made of two recordings, both free of rights:

- **The broadcast.** Voice of America, *VOA60 Extra: Pricey Super Bowl Tickets*, seconds 1 to 61.
  A work of the United States government, in the public domain.
  <https://commons.wikimedia.org/wiki/File:VOA60_Extra-_Pricey_Super_Bowl_Tickets.webm>
- **The room.** *IR Echo pop - Couch pos* by Sadiquecat, on Freesound, CC0 1.0: the impulse response
  of a living room of 525 × 300 × 275 cm, measured with a sine sweep from an Amazon Echo Pop to a
  microphone on the couch. Its reverberation falls 60 dB in about 0.4 s.
  <https://freesound.org/s/843704/>

The broadcast is convolved with the room's response (what the room does to any sound that speaker
plays), its two ends faded over 50 ms so the loop has no seam, and its peak set to 20000 of 32767.
Until 2026-11 the television was one clean voice read by the caller's own vendor and turned down:
to a microphone that is a second person speaking quietly into it, which no call has and no model
of a room can tell from the caller.
