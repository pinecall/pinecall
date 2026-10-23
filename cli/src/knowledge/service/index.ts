/** Knowledge: the documents an agent searches, a contact's memory, the recall and extraction goldens. */

export type { ContactFact, ContactMemory, ExtractionGolden, ExtractionRun, Forgotten, KnowledgeList, KnowledgePushed, KnowledgeScore, KnowledgeUses, MemoryScore, TuningAnswer } from "../../api/knowledge.js";
export { CASES, casesIn, matching, NO_CASES, questionsOf } from "./cases.js";
export { PullDocsInput, pullDocs, RemoveDocInput, removeDoc, type DocRemoved, type DocsPulled, type PulledFile } from "./checkout.js";
export {
  AttachBaseInput,
  attachBase,
  DetachBaseInput,
  detachBase,
  dropBase,
  EvalDocsInput,
  evalDocs,
  kReadWith,
  listAttached,
  listBases,
  markdownUnder,
  NO_DIRECTORY,
  NO_MARKDOWN,
  NOT_ATTACHED,
  ONLY_README,
  PushDocsInput,
  pushDocs,
  README,
  type BaseAttached,
  type DocsPushed,
  type DocsSkipped,
} from "./docs.js";
export { EvalMemoryInput, evalMemory, forgetContact, PolicyInput, policy, SAY_YES, showContact, type ContactRemembered, type Policy } from "./memory.js";
export { RememberInput, remember } from "./remember.js";
export { cornerRead, readSettings, writeCorner, type CornerWritten } from "./settings.js";
