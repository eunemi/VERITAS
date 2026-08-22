import Link from "next/link";
import { Band, Slug } from "./layout";
import { neighboursOf, type DeskDefinition } from "@/lib/desks";

interface Destination {
  label: string;
  title: string;
  href: string;
}

/**
 * Two doors out of the record: the desk before and the desk after. When there is
 * no neighbour in one direction the cell offers the index or a full
 * investigation, so neither side is ever a dead end.
 */
export function DeskNavigation({ desk }: { desk: DeskDefinition }) {
  const { previous, next } = neighboursOf(desk.id);

  const back: Destination = previous
    ? {
        label: `Agent ${previous.number} — previous desk`,
        title: previous.titleLines.join(" "),
        href: `/intel/${previous.id}`,
      }
    : { label: "Index", title: "All six desks", href: "/intel" };

  const forward: Destination = next
    ? {
        label: `Agent ${next.number} — next desk`,
        title: next.titleLines.join(" "),
        href: `/intel/${next.id}`,
      }
    : { label: "Every desk at once", title: "Open an investigation", href: "/investigate" };

  return (
    <Band className="bg-ink-black text-parchment" inner="grid sm:grid-cols-2">
      {[back, forward].map((destination, index) => (
        <Link
          key={destination.href}
          href={destination.href}
          className={`group py-stack-lg transition-colors hover:text-gold-foil focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-gold-foil ${
            index === 1
              ? "border-t border-parchment/15 sm:border-t-0 sm:border-l sm:pl-gutter sm:text-right"
              : "sm:pr-gutter"
          }`}
        >
          <Slug className="text-parchment/45">{destination.label}</Slug>
          <p className="font-headline-md mt-3 text-[26px] leading-[1.1] font-normal italic">
            {index === 1 ? <>{destination.title} &rarr;</> : <>&larr; {destination.title}</>}
          </p>
        </Link>
      ))}
    </Band>
  );
}
