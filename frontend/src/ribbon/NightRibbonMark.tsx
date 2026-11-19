/**
 * The Night Ribbon as a decorative mark (docs/design-direction.md).
 *
 * A horizontal overnight line with rings at planned times: filled rings
 * reported, a hollow ring stayed silent and is joined to its deadline by a
 * dotted gap line, and the vertical morning line marks the digest time. This
 * static version carries the signature visual into sign-in, empty states and
 * the 404 page; the live ribbon with real occurrences arrives in phase C8.
 * It is decorative: aria-hidden, no data.
 */
import './ribbon.css';

export interface NightRibbonMarkProps {
  readonly width?: number;
  /** 'hero' for the sign-in panel, 'empty' for empty states (quieter). */
  readonly variant?: 'hero' | 'empty';
  readonly className?: string;
}

interface Ring {
  readonly x: number;
  readonly kind: 'verified' | 'warning' | 'hollow' | 'failed';
}

// Positions along a 320-unit line (18:00 on the left, 12:00 on the right).
const RINGS: readonly Ring[] = [
  { x: 28, kind: 'verified' },
  { x: 74, kind: 'verified' },
  { x: 118, kind: 'warning' },
  { x: 160, kind: 'verified' },
  { x: 206, kind: 'hollow' },
  { x: 258, kind: 'verified' },
];
const MORNING_X = 282;
const RADIUS = 9;

export function NightRibbonMark({ width = 320, variant = 'hero', className }: NightRibbonMarkProps) {
  const height = 96;
  const classes = ['co-ribbon-mark', `co-ribbon-mark--${variant}`];
  if (className) {
    classes.push(className);
  }
  return (
    <svg
      className={classes.join(' ')}
      width={width}
      height={(width / 320) * height}
      viewBox={`0 0 320 ${height}`}
      aria-hidden="true"
      focusable="false"
    >
      <rect className="co-ribbon-mark__night" x="0" y="0" width="320" height={height} rx="12" />
      <line className="co-ribbon-mark__line" x1="12" y1="48" x2="308" y2="48" />
      {Array.from({ length: 7 }, (_, index) => (
        <line
          key={index}
          className="co-ribbon-mark__tick"
          x1={12 + index * 49.3}
          y1="70"
          x2={12 + index * 49.3}
          y2="76"
        />
      ))}
      {RINGS.map((ring) => {
        if (ring.kind === 'hollow') {
          return (
            <g key={ring.x}>
              <line
                className="co-ribbon-mark__gap"
                x1={ring.x + RADIUS + 2}
                y1="48"
                x2={MORNING_X - 4}
                y2="48"
              />
              <circle className="co-ribbon-mark__ring co-ribbon-mark__ring--hollow" cx={ring.x} cy="48" r={RADIUS} />
            </g>
          );
        }
        return (
          <circle
            key={ring.x}
            className={`co-ribbon-mark__ring co-ribbon-mark__ring--${ring.kind}`}
            cx={ring.x}
            cy="48"
            r={RADIUS}
          />
        );
      })}
      <line className="co-ribbon-mark__morning" x1={MORNING_X} y1="16" x2={MORNING_X} y2="80" />
    </svg>
  );
}
