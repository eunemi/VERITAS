/**
 * Seeded pseudo-random numbers.
 *
 * Waveforms and filmstrips need to look irregular but must render identically on
 * the server and the client, and must not change between renders. `Math.random()`
 * does neither, so everything irregular in the desks is derived from a seed.
 */

/** FNV-1a. Small, fast, good enough to spread short strings like file names. */
export function hashString(input: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i++) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

/** Mulberry32. Returns a generator of floats in [0, 1). */
export function seededRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * An audio-like envelope: `count` samples in [min, max], smoothed so adjacent
 * samples relate to each other the way a real waveform's do.
 */
export function seededEnvelope(
  seed: string,
  count: number,
  min = 0.12,
  max = 1,
): number[] {
  const next = seededRandom(hashString(seed));
  const out: number[] = [];
  let level = 0.5;
  for (let i = 0; i < count; i++) {
    // Drift towards a new target rather than jumping, so the shape reads as speech.
    level += (next() - 0.5) * 0.55;
    level = Math.min(1, Math.max(0, level));
    // Taper the very start and end, as a recording does.
    const taper = Math.sin((Math.PI * (i + 0.5)) / count);
    out.push(min + (max - min) * level * (0.35 + 0.65 * taper));
  }
  return out;
}
