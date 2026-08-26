import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/PageHeader";
import { StoryCard } from "@/components/ui/StoryCard";
import { SectionHead, Slug, Spread } from "@/components/agents/shared/layout";
import { DESK_ISSUE } from "@/lib/desks";

export const metadata: Metadata = {
  title: "Economy",
  description:
    "Verified financial intelligence: the readings as filed, the anomaly index behind them, and the desk record for every story.",
};

/**
 * The four readings.
 *
 * Each one used to print in four separately-styled parts — a 10px label at 50%
 * ink, a 60px figure, a 12px direction glyph, and a 10px footnote at 35% — which
 * is four sizes and four ink levels for one number, four times over. It is three
 * parts now: what it measures, the figure, and one line saying which way and
 * against what. The arrow glyphs are gone: "+1.4%" already says which way, and
 * the en dash that stood in for "flat" said nothing at all.
 */
const READINGS = [
  {
    label: "Global trade index",
    value: "114.2",
    change: "+1.4%",
    tone: "text-trust-green",
    against: "against the July close",
  },
  {
    label: "Inflation, core",
    value: "2.8%",
    change: "+0.2%",
    tone: "text-alert-crimson",
    against: "year on year",
  },
  {
    label: "Synthetic market volatility",
    value: "42.1",
    change: "High",
    tone: "text-secondary",
    against: "on the Veritas composite",
  },
  {
    label: "Veritas trust yield",
    value: "4.88%",
    /* This was `text-ink-black/55`, which is 3.9:1 on the paper ground. A figure
       the desk calls steady still has to be readable. */
    change: "Stable",
    tone: "text-ink-black/70",
    against: "over the rolling 30 days",
  },
] as const;

/**
 * Seven filed readings of the anomaly index, oldest first. The chart below is
 * drawn from this array, so the line and the printed figures cannot disagree —
 * the old one was a hand-written SVG path with a "7-day" caption attached.
 *
 * The date is split because the figures print in seven equal columns: at 375px
 * that is 48px a column, and "22 AUG" set as a tracked mono label needs every one
 * of them. The month is dropped on small screens, where the section note above
 * already says which week is being read.
 */
const ANOMALY_SERIES = [
  { day: "16", month: "Aug", value: 31 },
  { day: "17", month: "Aug", value: 38 },
  { day: "18", month: "Aug", value: 34 },
  { day: "19", month: "Aug", value: 52 },
  { day: "20", month: "Aug", value: 47 },
  { day: "21", month: "Aug", value: 68 },
  { day: "22", month: "Aug", value: 61 },
];

const FIRST = ANOMALY_SERIES[0];
const LAST = ANOMALY_SERIES[ANOMALY_SERIES.length - 1];

const FLOOR = 0;
const CEILING = 80;

/**
 * Plot points on a 0–100 box, so the SVG can stretch to any width.
 *
 * Each reading sits at the centre of its column rather than at `index / (n - 1)`.
 * That older spacing put the first reading hard against the left edge and the
 * last against the right, while the figures underneath are centred in seven equal
 * columns — so every printed figure stood beside a point that was not its own,
 * and the two ends were out by half a column.
 */
const STEP = 100 / ANOMALY_SERIES.length;
const PLOTTED = ANOMALY_SERIES.map((reading, index) => {
  const x = STEP * (index + 0.5);
  const y = 100 - ((reading.value - FLOOR) / (CEILING - FLOOR)) * 100;
  return { x, y };
});

const POINTS = PLOTTED.map(({ x, y }) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ");

/** The area under the line, closed on the baseline beneath the end readings. */
const AREA = `${PLOTTED[0].x.toFixed(2)},100 ${POINTS} ${PLOTTED[PLOTTED.length - 1].x.toFixed(2)},100`;

const HIGH = Math.max(...ANOMALY_SERIES.map((reading) => reading.value));
const LOW = Math.min(...ANOMALY_SERIES.map((reading) => reading.value));

export default function EconomyPage() {
  return (
    <main className="min-h-screen bg-background">
      <PageHeader
        section="Economy"
        standing="Financial intelligence"
        kicker="Four readings, as filed"
        title={["The economy,", "without the noise."]}
        lede="Market figures read against the record: what the desks could verify, what they could not, and the anomaly index sitting behind the numbers."
      />

      <Spread className="pb-stack-xl">
        <SectionHead title="The readings" note={`Filed ${DESK_ISSUE}`} />

        {/* The first reading used to carry a crimson left rule and the other three
            a grey one, which put the emphasis on whichever figure happened to be
            listed first. All four are ruled the same: none of them outranks the
            others. */}
        <dl className="mt-stack-md grid gap-x-gutter gap-y-stack-lg sm:grid-cols-2 lg:grid-cols-4">
          {READINGS.map((reading) => (
            <div key={reading.label} className="border-t border-ink-black/25 pt-stack-sm">
              <dt>
                <Slug className="text-ink-black/70">{reading.label}</Slug>
              </dt>
              <dd className="font-masthead tabular mt-2 text-[34px] leading-none font-bold text-ink-black md:text-[40px]">
                {reading.value}
              </dd>
              <dd className="font-body-sm text-body-sm mt-2.5">
                <span className={reading.tone}>{reading.change}</span>{" "}
                <span className="text-ink-black/70">{reading.against}</span>
              </dd>
            </div>
          ))}
        </dl>
      </Spread>

      <Spread className="pb-stack-xl">
        <SectionHead
          title="Trading anomaly index"
          note={`Seven days to ${DESK_ISSUE} · high ${HIGH}, low ${LOW}`}
        />

        {/* The plot used to sit on a ruled grid at 50% opacity — a graticule with
            no axis labels on either edge, so it measured nothing and only put
            forty lines behind the one line worth reading. The plot is bounded by
            two hairlines and the figures are printed underneath. */}
        <div className="mt-stack-md h-40 w-full border-y border-ink-black/25 md:h-52">
          <svg
            className="h-full w-full"
            preserveAspectRatio="none"
            viewBox="0 0 100 100"
            role="img"
            aria-label={`Anomaly index over seven days, rising from ${FIRST.value} on ${FIRST.day} ${FIRST.month} to ${LAST.value} on ${LAST.day} ${LAST.month}.`}
          >
            <polygon points={AREA} fill="rgba(183, 16, 50, 0.07)" />
            <polyline
              points={POINTS}
              fill="none"
              stroke="var(--color-secondary)"
              strokeWidth="1.5"
              vectorEffect="non-scaling-stroke"
            />
          </svg>
        </div>

        <ol className="mt-stack-sm grid grid-cols-7">
          {ANOMALY_SERIES.map((reading) => (
            <li key={reading.day} className="flex flex-col gap-1 text-center">
              <Slug className="tabular text-ink-black">{reading.value}</Slug>
              <Slug className="tabular text-ink-black/70">
                {reading.day}
                <span className="hidden sm:inline"> {reading.month}</span>
              </Slug>
            </li>
          ))}
        </ol>
      </Spread>

      <Spread className="pb-stack-xl">
        <SectionHead title="Market intelligence" note="Two records filed this week" />

        <div className="mt-stack-md grid grid-cols-1 gap-x-gutter gap-y-stack-lg md:grid-cols-2">
          <StoryCard
            category="Markets"
            headline="Flash crash traced to a coordinated deepfake audio release"
            description="A $200 billion wipeout in the semiconductor sector was triggered by an algorithmic response to synthetic audio clips attributed to four chief executives. The audio desk found the recordings were generated end to end."
            source="Bloomberg / Veritas audit"
            date="21 Aug 2026"
            verificationStatus="VERIFIED"
            desk="audio"
          />
          <StoryCard
            category="Currency"
            headline="Digital currency adoption figures do not match the network"
            description="Official retail adoption figures for the new central bank currency appear inflated: 40% of the transactions counted originate from automated nodes rather than retail wallets."
            source="Veritas Intel"
            date="20 Aug 2026"
            verificationStatus="UNDER REVIEW"
            desk="fact-check"
          />
        </div>
      </Spread>
    </main>
  );
}
