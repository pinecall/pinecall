/** Agents: what the org set over the class, per corner and versioned; the lexicon; the pipeline; the processes; the voices. */

export { cornerName, cornerRead, cornerWritten, holdsACorner, readSettings, rowToStartFrom, versionGuarded, writeCorner, type Change, type CornerWritten, type TuningAnswer, type TuningBody, type TuningRow } from "./corners.js";
export { AfterInput, chooseMelody, showMelody, uploadMelody, waitBeforeMelody, type HoldMelody } from "./melody.js";
export { listWalks, playWalk, type WalkListed, type WalkPlayed } from "./walks.js";
export { hearWords, lexiconHistory, removeWords, sayWord, SayWordInput, showLexicon, WordsInput, type LexiconAnswer, type LexiconHistory, type LexiconRow, type Words } from "./lexicon.js";
export {
  countTools,
  defaultVoiceVendor,
  killAgent,
  listApps,
  listVoices,
  ListVoicesInput,
  playVoice,
  sampleVoice,
  SampleVoiceInput,
  showPipeline,
  stopApp,
  type AppProcess,
  type KilledAgent,
  type ListedVoice,
  type PipelineReport,
  type VoicePlayed,
  type VoiceSampled,
} from "./running.js";
export {
  agentNamed,
  clearSettings,
  DECLARED_AS,
  END_OF_TURN,
  FIELDS,
  fieldsOf,
  openingOf,
  pullSettings,
  pushSettings,
  readKnowledge,
  rollbackSettings,
  setSettings,
  settingsDiff,
  settingsHistory,
  SettingsInput,
  showSettings,
  WIRE,
  writeKnowledge,
  WriteOptions,
  type Field,
  type Pulled,
} from "./settings.js";
