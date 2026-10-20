/** What a test room runs other than the agent's own settings: its voice and models, asked for at its token and kept nowhere. */

/** The knobs a test room may ask for (the runtime's `TEST_KNOBS`); a model is `vendor/model`, as the settings say it. */
export interface TestValues {
  stt?: string;
  llm?: string;
  tts?: string;
  voice?: string;
  language?: string;
  temperature?: number;
}

/** Whether a test room asks for anything. */
export function asking(values: TestValues | null | undefined): values is TestValues {
  return values !== null && values !== undefined && Object.keys(values).length > 0;
}

/** What is asked, in a few words: `voice lucia · llm google/gemini-2.5-flash`. */
export function said(values: TestValues): string {
  const names: [string, string | number | undefined][] = [
    ["voice", values.voice],
    ["voice vendor", values.tts],
    ["thinks", values.llm],
    ["hears", values.stt],
    ["language", values.language],
    ["temperature", values.temperature],
  ];
  return names.flatMap(([name, value]) => (value === undefined ? [] : [`${name} ${String(value)}`])).join(" · ");
}
