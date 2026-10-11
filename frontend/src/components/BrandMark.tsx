import Image from "next/image";

interface BrandMarkProps {
  size?: number;
  className?: string;
  priority?: boolean;
}

/** The Veritas sight mark used by the masthead, footer, and app icon. */
export function BrandMark({ size = 44, className, priority = false }: BrandMarkProps) {
  return (
    <Image
      src="/veritas-mark.svg"
      alt=""
      width={size}
      height={size}
      priority={priority}
      className={className}
    />
  );
}
