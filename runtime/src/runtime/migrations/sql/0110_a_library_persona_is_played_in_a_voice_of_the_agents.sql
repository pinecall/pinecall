-- An agent may give one of Pinecall's personas the voice its lines are read in, as it gives it a
-- model: persona_switches gains `tts` (the vendor) and `voice` (its id), null for the runtime's
-- choice, a voice the agent does not have. The agent's row wins over the org's. Expanding only.
--
-- Locks and time: the ALTER takes ACCESS EXCLUSIVE on persona_switches for the instant of adding
-- two nullable columns (no rewrite); the table holds a few rows an org.

ALTER TABLE persona_switches
    ADD COLUMN tts text,
    ADD COLUMN voice text;
