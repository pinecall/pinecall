// JSX runtime whitespace rules.

import { describe, expect, it } from "vitest";

import { renderToText } from "../../src/views/jsx-runtime.js";
import { Section } from "../../src/views/components.js";

describe("the JSX runtime renders text, not DOM", () => {
  it("renders a paragraph as one line", () => {
    expect(renderToText(<p>Saluda y pide el nombre.</p>)).toBe("Saluda y pide el nombre.");
  });

  it("separates two sibling paragraphs with one blank line", () => {
    const text = renderToText(
      <>
        <p>Primero.</p>
        <p>Segundo.</p>
      </>,
    );
    expect(text).toBe("Primero.\n\nSegundo.");
  });

  it("renders nothing at all for null, false and undefined", () => {
    const text = renderToText(
      <>
        {null}
        {false}
        {undefined}
        <p>Lo único que queda.</p>
      </>,
    );
    expect(text).toBe("Lo único que queda.");
  });

  it("keeps the spaces the author wrote between interpolations", () => {
    const name = "Ana";
    expect(renderToText(<p>{name} tiene cita el {"martes"}.</p>)).toBe("Ana tiene cita el martes.");
  });

  it("collapses the newlines and the indentation a long paragraph was written over", () => {
    const text = renderToText(
      <p>
        Una frase larga que el autor partió en dos líneas para leerla mejor.
      </p>,
    );
    expect(text).toBe("Una frase larga que el autor partió en dos líneas para leerla mejor.");
  });

  it("trims a bare string at its ends without touching its inside", () => {
    expect(renderToText("  dos  espacios  dentro  ")).toBe("dos  espacios  dentro");
  });

  it("drops an empty paragraph instead of leaving a blank line behind", () => {
    expect(renderToText(<><p>{""}</p><p>Sola.</p></>)).toBe("Sola.");
  });

  it("gives a section its title as a heading", () => {
    expect(renderToText(<Section title="Agenda"><p>Hoy.</p></Section>)).toBe("## Agenda\n\nHoy.");
  });
});
