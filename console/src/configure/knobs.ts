/**
 * The vendor settings a person may change from the console, by stage and by the argument's name.
 * A list of what is shown, never of what is hidden: a plugin's argument that is not named here (where its
 * requests go, whose cloud it runs on, its credentials) is drawn nowhere.
 */

import type { IconName } from "../shell/icons";
import type { Modality } from "./vendors";

export interface Knob {
  title: string;
  about: string;
  icon: IconName;
  /** Where the argument's range is the same at every vendor that takes it: drawn as a slider. */
  range?: { min: number; max: number; step: number; rest: number; ends?: readonly [string, string] };
}

const MAX_TOKENS: Knob = { title: "Max tokens", about: "The most tokens the assistant can generate in each turn of the conversation.", icon: "coins" };
const SEED: Knob = { title: "Seed", about: "Asks the model to repeat the same answer to the same words, as far as it can.", icon: "hash" };
const PENALTY = { min: -2, max: 2, step: 0.1, rest: 0 };
const PROMPT: Knob = { title: "Prompt", about: "Words that tell the transcriber what the calls are about.", icon: "type" };
const SPEED: Knob = { title: "Speed", about: "How fast the voice speaks. Each vendor has its own range.", icon: "gauge" };
const ENDPOINT_DELAY = "How long the transcriber waits, in milliseconds, before it decides the caller is done.";

export const KNOBS: Record<Modality, Readonly<Record<string, Knob>>> = {
  llm: {
    max_tokens: MAX_TOKENS,
    max_completion_tokens: MAX_TOKENS,
    max_output_tokens: MAX_TOKENS,
    reasoning_effort: { title: "Reasoning effort", about: "How much it thinks before it answers. Less answers sooner, which a call feels.", icon: "brain" },
    verbosity: { title: "Verbosity", about: "How long its answers tend to be.", icon: "type" },
    top_p: { title: "Top P", about: "Keeps only the likeliest words, up to this share of the probability.", icon: "settings", range: { min: 0, max: 1, step: 0.05, rest: 1 } },
    top_k: { title: "Top K", about: "Chooses each word from only this many of the likeliest.", icon: "settings" },
    presence_penalty: { title: "Presence penalty", about: "Above zero, it moves on to new subjects more readily.", icon: "settings", range: PENALTY },
    frequency_penalty: { title: "Frequency penalty", about: "Above zero, it repeats the same words less.", icon: "settings", range: PENALTY },
    seed: SEED,
    random_seed: SEED,
    parallel_tool_calls: { title: "Parallel tool calls", about: "Lets the model ask for several tools at once.", icon: "tools" },
    caching: { title: "Prompt caching", about: "Keeps the instructions cached between turns: cheaper and faster on long prompts.", icon: "bolt" },
  },
  stt: {
    punctuate: { title: "Punctuation", about: "Adds punctuation to what it hears.", icon: "type" },
    smart_format: { title: "Smart format", about: "Writes dates, amounts and phone numbers the way they are read.", icon: "type" },
    numerals: { title: "Numerals", about: "Writes numbers as digits.", icon: "hash" },
    filler_words: { title: "Filler words", about: "Keeps the “um” and “uh” in the transcript.", icon: "type" },
    profanity_filter: { title: "Profanity filter", about: "Masks swear words in the transcript.", icon: "privacy" },
    endpointing_ms: { title: "Silence before a turn ends", about: ENDPOINT_DELAY, icon: "clock" },
    utterance_end_ms: { title: "Utterance end", about: "Milliseconds of no new words that mark the end of what was said.", icon: "clock" },
    max_endpoint_delay_ms: { title: "Longest wait for a turn's end", about: ENDPOINT_DELAY, icon: "clock" },
    endpoint_sensitivity: { title: "Endpoint sensitivity", about: "How readily it decides the caller has finished.", icon: "gauge" },
    min_turn_silence: { title: "Shortest silence for a turn", about: "Milliseconds of silence before it may end a turn.", icon: "clock" },
    max_turn_silence: { title: "Longest silence for a turn", about: "Milliseconds of silence that always end a turn.", icon: "clock" },
    end_of_turn_confidence_threshold: { title: "End of turn confidence", about: "How sure it must be that the caller is done.", icon: "gauge", range: { min: 0, max: 1, step: 0.05, rest: 0.5 } },
    min_confidence_threshold: { title: "Minimum confidence", about: "Words it is less sure of than this are dropped.", icon: "gauge", range: { min: 0, max: 1, step: 0.05, rest: 0.65 } },
    endpointing_sensitivity: { title: "Endpoint sensitivity", about: "How readily it decides the caller has finished.", icon: "gauge" },
    mode: { title: "Mode", about: "Trades latency against accuracy.", icon: "gauge" },
    voice_focus: { title: "Voice focus", about: "Tells it how far from the microphone the caller is.", icon: "ear" },
    tag_audio_events: { title: "Audio events", about: "Marks laughter, applause and the like in the transcript.", icon: "ear" },
    no_verbatim: { title: "Clean transcript", about: "Leaves out false starts and non-speech sounds.", icon: "type" },
    spoken_punctuation: { title: "Spoken punctuation", about: "Writes “comma” as a comma when the caller says it.", icon: "type" },
    prompt: PROMPT,
  },
  tts: {
    speed: SPEED,
    speaking_rate: SPEED,
    speed_alpha: { title: "Speed", about: "Above 1 speaks slower, below 1 faster.", icon: "gauge" },
    pitch: { title: "Pitch", about: "How high or low the voice sits.", icon: "speaker" },
    volume: { title: "Volume", about: "How loud the voice is.", icon: "speaker" },
    volume_gain_db: { title: "Volume gain", about: "Louder or softer, in decibels.", icon: "speaker" },
    emotion: { title: "Emotion", about: "The feelings it speaks with, separated by commas.", icon: "speaker" },
    instructions: { title: "Delivery", about: "How the voice should speak, in a sentence.", icon: "type" },
    prompt: { title: "Delivery", about: "How the voice should speak, in a sentence.", icon: "type" },
    delivery_mode: { title: "Delivery mode", about: "Steadier, or more expressive.", icon: "speaker" },
    streaming_latency: { title: "Latency optimization", about: "From 0 to 4: higher starts speaking sooner and may mispronounce more.", icon: "bolt" },
    reduce_latency: { title: "Reduce latency", about: "Starts speaking sooner.", icon: "bolt" },
    reduce_silence: { title: "Reduce silence", about: "Trims the pauses inside what it says.", icon: "clock" },
    apply_text_normalization: { title: "Text normalization", about: "Reads numbers and dates out in words.", icon: "type" },
    text_normalization: { title: "Text normalization", about: "Reads numbers and dates out in words.", icon: "type" },
    enable_ssml_parsing: { title: "SSML", about: "Reads SSML tags in the text as instructions.", icon: "type" },
    enable_ssml: { title: "SSML", about: "Reads SSML tags in the text as instructions.", icon: "type" },
  },
};
