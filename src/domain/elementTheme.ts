/**
 * Element theme map — single source of truth for all element-type styling.
 * Used by BaseBoostView and any future component that needs element colours.
 */

export interface ElementTheme {
  /** Base accent colour (use for text, icon tint, glow) */
  color: string
  /** Stronger variant for hover borders / glow peak */
  colorStrong: string
  /** Radial glow CSS string — drop behind pal icon */
  glow: string
  /** Section-corner gradient for panel background accent */
  gradient: string
  /** Inline SVG path (viewBox 0 0 24 24) representing the element */
  svgPath: string
  /** Human-readable label */
  label: string
}

export const ELEMENT_THEME: Record<string, ElementTheme> = {
  Fire: {
    color: '#f97316',
    colorStrong: '#fb923c',
    glow: 'radial-gradient(circle at 50% 60%, rgba(249,115,22,0.45) 0%, transparent 70%)',
    gradient: 'radial-gradient(ellipse at 0% 100%, rgba(249,115,22,0.14) 0%, transparent 55%)',
    // Flame shape
    svgPath:
      'M12 2C9.5 6 7 8.5 7 12a5 5 0 0 0 10 0c0-1.5-.5-3-1.5-4.5C14 9 13 10 12 10c1-2 0-5-0-8Z',
    label: 'Fire',
  },
  Grass: {
    color: '#22c55e',
    colorStrong: '#4ade80',
    glow: 'radial-gradient(circle at 50% 60%, rgba(34,197,94,0.40) 0%, transparent 70%)',
    gradient: 'radial-gradient(ellipse at 0% 100%, rgba(34,197,94,0.12) 0%, transparent 55%)',
    // Leaf shape
    svgPath:
      'M17 8C8 10 5.9 16.17 3.82 19.82L5.71 21l1-1.29c.19.16.39.31.59.44A9 9 0 0 0 21 12c0-5.5-4-10-4-10s0 4-4 6Z',
    label: 'Grass',
  },
  Ground: {
    color: '#d97706',
    colorStrong: '#f59e0b',
    glow: 'radial-gradient(circle at 50% 60%, rgba(217,119,6,0.40) 0%, transparent 70%)',
    gradient: 'radial-gradient(ellipse at 0% 100%, rgba(217,119,6,0.12) 0%, transparent 55%)',
    // Mountain / triangle
    svgPath: 'M2 20h20L12 4 2 20Z',
    label: 'Ground',
  },
  Electric: {
    color: '#eab308',
    colorStrong: '#facc15',
    glow: 'radial-gradient(circle at 50% 60%, rgba(234,179,8,0.45) 0%, transparent 70%)',
    gradient: 'radial-gradient(ellipse at 0% 100%, rgba(234,179,8,0.14) 0%, transparent 55%)',
    // Lightning bolt
    svgPath: 'M13 2L4.5 13.5H11L10 22l8.5-11.5H13L13 2Z',
    label: 'Electric',
  },
  Water: {
    color: '#3b82f6',
    colorStrong: '#60a5fa',
    glow: 'radial-gradient(circle at 50% 60%, rgba(59,130,246,0.45) 0%, transparent 70%)',
    gradient: 'radial-gradient(ellipse at 0% 100%, rgba(59,130,246,0.14) 0%, transparent 55%)',
    // Water drop
    svgPath: 'M12 2C12 2 5 10 5 15a7 7 0 0 0 14 0C19 10 12 2 12 2Z',
    label: 'Water',
  },
  Ice: {
    color: '#67e8f9',
    colorStrong: '#a5f3fc',
    glow: 'radial-gradient(circle at 50% 60%, rgba(103,232,249,0.40) 0%, transparent 70%)',
    gradient: 'radial-gradient(ellipse at 0% 100%, rgba(103,232,249,0.12) 0%, transparent 55%)',
    // Snowflake (simplified 6-pointed)
    svgPath: 'M12 2v20M2 12h20M5.636 5.636l12.728 12.728M18.364 5.636 5.636 18.364',
    label: 'Ice',
  },
  Dark: {
    color: '#a855f7',
    colorStrong: '#c084fc',
    glow: 'radial-gradient(circle at 50% 60%, rgba(168,85,247,0.45) 0%, transparent 70%)',
    gradient: 'radial-gradient(ellipse at 0% 100%, rgba(168,85,247,0.14) 0%, transparent 55%)',
    // Crescent moon
    svgPath: 'M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79Z',
    label: 'Dark',
  },
  Dragon: {
    color: '#ec4899',
    colorStrong: '#f472b6',
    glow: 'radial-gradient(circle at 50% 60%, rgba(236,72,153,0.45) 0%, transparent 70%)',
    gradient: 'radial-gradient(ellipse at 0% 100%, rgba(236,72,153,0.14) 0%, transparent 55%)',
    // Dragon wing / spiral
    svgPath:
      'M12 2a9 9 0 0 1 9 9c0 2.5-1 4.7-2.6 6.3L12 22l-6.4-4.7A8.97 8.97 0 0 1 3 11 9 9 0 0 1 12 2Z',
    label: 'Dragon',
  },
  Neutral: {
    color: '#94a3b8',
    colorStrong: '#cbd5e1',
    glow: 'radial-gradient(circle at 50% 60%, rgba(148,163,184,0.35) 0%, transparent 70%)',
    gradient: 'radial-gradient(ellipse at 0% 100%, rgba(148,163,184,0.10) 0%, transparent 55%)',
    // Simple circle
    svgPath: 'M12 2a10 10 0 1 0 0 20A10 10 0 0 0 12 2Z',
    label: 'Neutral',
  },
}

/** Ice snowflake uses strokes not fill — mark those element keys */
export const ELEMENT_STROKE_ONLY = new Set(['Ice'])
