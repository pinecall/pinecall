/** A web visitor as a person reads them: the flag of their country, its name, and their browser in two words. */

/** The flag of a country, from its two letters (ISO 3166 alpha-2): the emoji a browser draws for its regional indicators. */
export function flagOf(country: string | null | undefined): string | null {
  if (country == null || !/^[A-Za-z]{2}$/.test(country)) return null;
  return String.fromCodePoint(...[...country.toUpperCase()].map((letter) => 0x1f1e6 + letter.charCodeAt(0) - 65));
}

/** The country's name in English, as the console is written; its two letters where the browser knows no name. */
export function countryName(country: string | null | undefined): string | null {
  if (country == null) return null;
  try {
    return new Intl.DisplayNames(["en"], { type: "region" }).of(country.toUpperCase()) ?? country;
  } catch {
    return country;
  }
}

// Read in this order: Edge and Opera say Chrome too, Chrome says Safari too.
const BROWSERS: readonly (readonly [RegExp, string])[] = [
  [/Edg(?:e|A|iOS)?\//, "Edge"],
  [/OPR\/|Opera/, "Opera"],
  [/SamsungBrowser\//, "Samsung Internet"],
  [/Firefox\/|FxiOS\//, "Firefox"],
  [/Chrome\/|CriOS\//, "Chrome"],
  [/Safari\//, "Safari"],
];
const SYSTEMS: readonly (readonly [RegExp, string])[] = [
  [/iPhone|iPod/, "iPhone"],
  [/iPad/, "iPad"],
  [/Android/, "Android"],
  [/Windows/, "Windows"],
  [/Mac OS X|Macintosh/, "Mac"],
  [/CrOS/, "ChromeOS"],
  [/Linux/, "Linux"],
];

/** "Chrome on Android", "Safari on iPhone": a User-Agent as a person says it; null for none, the line itself for one not known. */
export function browserOf(userAgent: string | null | undefined): string | null {
  if (userAgent == null || userAgent.trim() === "") return null;
  const browser = BROWSERS.find(([said]) => said.test(userAgent))?.[1];
  const system = SYSTEMS.find(([said]) => said.test(userAgent))?.[1];
  if (browser === undefined && system === undefined) return userAgent.slice(0, 60);
  return [browser, system].filter((one) => one !== undefined).join(" on ");
}
