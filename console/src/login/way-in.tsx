/** The frame of every way in: the deployment's own name, logo and colour, as its gateway publishes them, beside a voice drawn in that colour. */

import { useEffect, useState, type CSSProperties, type ReactNode } from "react";

import { discovered, type Discovered } from "@pinecall/core/the-floor";
import { API_BASE } from "../lib/key";
import "./login.css";

export type Brand = NonNullable<Discovered["brand"]>;

// What a gateway answers when nobody has set a brand: Pinecall's own logo is drawn for it.
const THE_DEFAULT_NAME = "Pinecall";
const BARS = 72;
const KEPT_UNDER = "pinecall.brand";

// Drawn from what this browser last saw, so the logo is there on the first paint of every load.
function keptBrand(): Brand | null {
  try {
    const kept = window.localStorage.getItem(KEPT_UNDER);
    return kept === null ? null : (JSON.parse(kept) as Brand);
  } catch {
    return null;
  }
}

function keepBrand(brand: Brand): void {
  try {
    window.localStorage.setItem(KEPT_UNDER, JSON.stringify(brand));
  } catch {
    // Read again on the next load.
  }
}

// A colour an operator picks can be pale or dark: what is written on it is whichever reads.
function inkOn(accent: string): string {
  const [red, green, blue] = [1, 3, 5].map((at) => parseInt(accent.slice(at, at + 2), 16) / 255).map((one) => (one <= 0.03928 ? one / 12.92 : ((one + 0.055) / 1.055) ** 2.4));
  const light = 0.2126 * (red ?? 0) + 0.7152 * (green ?? 0) + 0.0722 * (blue ?? 0);
  return 1.05 / (light + 0.05) >= (light + 0.05) / 0.05 ? "#ffffff" : "#090a12";
}

/** The custom properties a page wears the brand's colour through. */
export function wornBy(brand: Pick<Brand, "accent">): CSSProperties {
  return { "--login-accent": brand.accent, "--login-on-accent": inkOn(brand.accent) } as CSSProperties;
}

/** The logo the deployment set; else Pinecall's where nobody set a brand; else its initial and name. */
export function BrandMark({ brand, small = false }: { brand: Brand; small?: boolean }): ReactNode {
  const pinecalls = brand.logo_url === null && brand.name === THE_DEFAULT_NAME;
  if (small) {
    if (pinecalls) return <img className="login-logo" src="/pinecall-mark-b219dacb.png" alt={brand.name} />;
    return (
      <span className="login-mark" role="img" aria-label={brand.name}>
        {brand.name.slice(0, 1).toUpperCase()}
      </span>
    );
  }
  if (brand.logo_url !== null) return <img className="login-logo" src={brand.logo_url} alt={brand.name} />;
  if (pinecalls) {
    return (
      <>
        <img className="login-logo login-logo-on-dark" src="/pinecall-logo-dark-966fa8a4.png" alt={brand.name} />
        <img className="login-logo login-logo-on-light" src="/pinecall-logo-6289e641.png" alt={brand.name} />
      </>
    );
  }
  return (
    <>
      <span className="login-mark" aria-hidden="true">
        {brand.name.slice(0, 1).toUpperCase()}
      </span>
      <span className="login-name">{brand.name}</span>
    </>
  );
}

/** The brand this gateway publishes: the one last seen at once, then the gateway's own. */
export function useBrand(): Brand | null {
  const [brand, setBrand] = useState<Brand | null>(keptBrand);
  useEffect(() => {
    let gone = false;
    void discovered(API_BASE).then((said) => {
      if (said.brand === undefined) return;
      keepBrand(said.brand);
      if (!gone) setBrand(said.brand);
    });
    return () => {
      gone = true;
    };
  }, []);
  return brand;
}

// Two slow waves beating against each other: it reads as somebody speaking, and never repeats by the bar.
function Voice(): ReactNode {
  return (
    <div className="login-voice" aria-hidden="true">
      {Array.from({ length: BARS }, (_, at) => {
        const swell = Math.abs(Math.sin(at * 0.31) * Math.cos(at * 0.11)) * 0.82 + 0.1;
        return <span key={at} style={{ height: `${Math.round(swell * 100)}%`, animationDelay: `${-((at * 137) % 2400)}ms` }} />;
      })}
    </div>
  );
}

// Pinecall's own sheet: its night sky with the console laid over it. A deployment with a brand keeps its voice.
function Sky(): ReactNode {
  return (
    <div className="login-art" aria-hidden="true">
      <img className="login-sky" src="/login-sky-d1fb0146.webp" alt="" />
      <img className="login-shot" src="/login-shot-5891b2fc.webp" alt="" />
    </div>
  );
}

function isPinecalls(brand: Brand | null): boolean {
  return brand === null || (brand.logo_url === null && brand.name === THE_DEFAULT_NAME);
}

export function WayIn({
  title,
  lede,
  children,
  aside,
  foot,
}: {
  title: string;
  lede?: ReactNode | undefined;
  children?: ReactNode | undefined;
  /** The ways out, under the form. */
  aside?: ReactNode | undefined;
  foot?: ReactNode | undefined;
}): ReactNode {
  const brand = useBrand();
  return (
    <div className="login" style={brand === null ? undefined : wornBy(brand)}>
      <div className="login-side">
        <div className="login-brand">{brand !== null && <BrandMark brand={brand} />}</div>
        <div className="login-in">
          <h1 className="login-title">{title}</h1>
          {lede !== undefined && <p className="login-lede">{lede}</p>}
          {children !== undefined && <div className="login-form">{children}</div>}
          {aside !== undefined && <p className="login-aside">{aside}</p>}
          {foot !== undefined && <p className="login-foot">{foot}</p>}
        </div>
      </div>
      <div className="login-sheet">{isPinecalls(brand) ? <Sky /> : <Voice />}</div>
    </div>
  );
}
