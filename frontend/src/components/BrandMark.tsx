interface BrandMarkProps {
  size?: number;
  className?: string;
  tone?: "light" | "dark";
}

/**
 * The Veritas sight mark used by the masthead and footer.
 *
 * This is intentionally inline rather than an image with a baked-in canvas. It
 * keeps the mark transparent and lets it stay legible on both paper and the
 * obsidian footer without ever bringing the old black square along with it.
 */
export function BrandMark({ size = 44, className, tone = "light" }: BrandMarkProps) {
  const isDark = tone === "dark";
  const ink = isDark ? "#F4EFE6" : "#1A1A1A";
  const cutout = isDark ? "#1A1A1A" : "#FEF9F0";
  const line = isDark ? "#D8D0C1" : "#1A1A1A";
  const accent = isDark ? "#D88876" : "#B71032";

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 256 256"
      width={size}
      height={size}
      className={className}
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <g stroke={line} strokeLinecap="square">
        <circle cx="128" cy="128" r="70" strokeOpacity="0.18" strokeWidth="1.5" />
        <circle cx="128" cy="128" r="58" strokeOpacity="0.62" strokeWidth="2" />
        <circle cx="128" cy="128" r="47" strokeOpacity="0.26" strokeWidth="1.5" />
        <path d="M128 30V62M128 194V226M30 128H62M194 128H226" strokeOpacity="0.7" strokeWidth="2" />
        <path d="M128 43V56M128 200V213M43 128H56M200 128H213" strokeOpacity="0.45" />
      </g>

      <path d="M128 48L135 61L128 74L121 61L128 48Z" fill={accent} />
      <path d="M68 70H108L128 126L148 70H188L143 184H113L68 70Z" fill={ink} />
      <path d="M86 70H108L128 126L148 70H170L137 159H119L86 70Z" fill={cutout} />
      <path d="M124 93L128 104L132 93L128 82L124 93Z" fill={accent} opacity="0.9" />
    </svg>
  );
}
