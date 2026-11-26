/** The end of a list that reads on by itself: when it comes into view, the page before is asked for. */

import { useEffect, useRef, type ReactNode } from "react";

// Asked a screen before the end is reached, so the rows are there by the time the reader gets to them.
const AHEAD = "600px";

/** Draws nothing but a line to watch, and asks `onOlder` each time it comes into view; nothing when there is no more. */
export function ReadsOn({ onOlder }: { onOlder: (() => void) | undefined }): ReactNode {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const watched = end.current;
    if (watched === null || onOlder === undefined) return;
    const seen = new IntersectionObserver((entries) => entries.some((one) => one.isIntersecting) && onOlder(), { rootMargin: AHEAD });
    seen.observe(watched);
    return () => seen.disconnect();
  }, [onOlder]);
  if (onOlder === undefined) return null;
  return (
    <div ref={end} className="calls-reads-on dash-quiet" aria-hidden="true">
      Reading older…
    </div>
  );
}
