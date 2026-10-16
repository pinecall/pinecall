-- An agent may play one of Pinecall's personas on a model of its choosing, as it switches it on or
-- off: persona_switches gains `llm`, `vendor/model`, null for the box's caller model. The agent's
-- row wins over the org's, as its switch does. Expanding only.
--
-- Locks and time: the ALTER takes ACCESS EXCLUSIVE on persona_switches for the instant of adding a
-- nullable column (no rewrite); the table holds a few rows an org.

ALTER TABLE persona_switches
    ADD COLUMN llm text;
