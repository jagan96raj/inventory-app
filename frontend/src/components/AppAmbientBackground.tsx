/**
 * Stylized animated backdrop inspired by warehouse bag stacks and a processing plant.
 * Reference photos are not used — this is original vector art only.
 */
type Props = {
  /** "app" = main shell (olive tint); "auth" = login hero (light on brand green) */
  variant?: "app" | "auth";
};

function BagStack({ x, y, w, h, rows, opacity = 1 }: { x: number; y: number; w: number; h: number; rows: number; opacity?: number }) {
  const bags = [];
  for (let r = 0; r < rows; r++) {
    const cols = Math.max(1, 3 - (r % 2));
    for (let c = 0; c < cols; c++) {
      const bx = x + c * (w * 0.92);
      const by = y - r * (h * 0.88);
      const top = by + h * 0.2;
      bags.push(
        <g key={`${r}-${c}`} opacity={opacity - r * 0.06}>
          <path
            d={`M${bx} ${by + h}V${top}l${w * 0.5} ${-h * 0.12}l${w * 0.5} ${h * 0.12}V${by + h}z`}
            fill="currentColor"
            fillOpacity={0.09}
            stroke="currentColor"
            strokeWidth="1.5"
            strokeOpacity={0.28}
          />
          <path
            d={`M${bx + w * 0.5} ${top - h * 0.06}l${w * 0.5} ${h * 0.12}l${-w * 0.5} ${h * 0.12}z`}
            fill="currentColor"
            fillOpacity={0.14}
          />
        </g>
      );
    }
  }
  return <g>{bags}</g>;
}

export default function AppAmbientBackground({ variant = "app" }: Props) {
  return (
    <div
      className={`app-ambient-bg app-ambient-bg--${variant}`}
      aria-hidden="true"
    >
      <svg
        className="app-ambient-bg__svg"
        viewBox="0 0 1100 720"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        preserveAspectRatio="xMaxYMax meet"
      >
        <defs>
          <pattern id="woven" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(24)">
            <path d="M0 4h8M4 0v8" stroke="currentColor" strokeOpacity="0.12" strokeWidth="0.6" />
          </pattern>
          <linearGradient id="floorFade" x1="0" y1="580" x2="0" y2="720" gradientUnits="userSpaceOnUse">
            <stop stopColor="currentColor" stopOpacity="0.06" />
            <stop offset="1" stopColor="currentColor" stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* floor */}
        <rect x="0" y="600" width="1100" height="120" fill="url(#floorFade)" />
        <line x1="40" y1="600" x2="1060" y2="600" stroke="currentColor" strokeOpacity="0.14" strokeWidth="1.5" />

        {/* —— Processing plant (right) — inspired by silos / elevators —— */}
        <g className="app-ambient-plant">
          {/* blue silo */}
          <rect x="820" y="180" width="120" height="200" rx="4" fill="#3a4027" fillOpacity="0.14" stroke="currentColor" strokeOpacity="0.2" strokeWidth="1.5" />
          <rect x="832" y="192" width="96" height="24" rx="2" fill="currentColor" fillOpacity="0.06" />

          {/* white elevator columns */}
          <rect x="700" y="120" width="36" height="480" rx="3" fill="currentColor" fillOpacity="0.05" stroke="currentColor" strokeOpacity="0.16" strokeWidth="1.2" className="app-ambient-elevator" />
          <rect x="760" y="100" width="36" height="500" rx="3" fill="currentColor" fillOpacity="0.06" stroke="currentColor" strokeOpacity="0.18" strokeWidth="1.2" className="app-ambient-elevator app-ambient-elevator--delay" />

          {/* overhead walkway */}
          <rect x="680" y="260" width="280" height="14" rx="2" fill="#454c2d" fillOpacity="0.12" stroke="currentColor" strokeOpacity="0.14" strokeWidth="1" />
          <line x1="690" y1="274" x2="690" y2="340" stroke="currentColor" strokeOpacity="0.12" strokeWidth="1.2" />
          <line x1="950" y1="274" x2="950" y2="340" stroke="currentColor" strokeOpacity="0.12" strokeWidth="1.2" />

          {/* red hopper accent */}
          <path
            d="M640 520h48l-12 36H652z"
            fill="#dc2626"
            fillOpacity="0.18"
            stroke="currentColor"
            strokeOpacity="0.2"
            strokeWidth="1.2"
          />
          <rect x="636" y="556" width="56" height="44" rx="3" fill="currentColor" fillOpacity="0.05" stroke="currentColor" strokeOpacity="0.16" strokeWidth="1.2" />

          {/* pipes / chutes */}
          <path d="M736 380h80v40l40 24v60" stroke="currentColor" strokeOpacity="0.14" strokeWidth="2" strokeLinecap="round" fill="none" />
          <path d="M880 380v100l-60 40" stroke="currentColor" strokeOpacity="0.12" strokeWidth="2" strokeLinecap="round" fill="none" />

          {/* grain flow dots */}
          <circle className="app-ambient-grain app-ambient-grain--1" cx="736" cy="382" r="3" fill="currentColor" fillOpacity="0.35" />
          <circle className="app-ambient-grain app-ambient-grain--2" cx="736" cy="382" r="2.5" fill="currentColor" fillOpacity="0.28" />
          <circle className="app-ambient-grain app-ambient-grain--3" cx="736" cy="382" r="2" fill="currentColor" fillOpacity="0.22" />

          {/* control panel blink */}
          <rect x="600" y="420" width="36" height="48" rx="3" fill="currentColor" fillOpacity="0.06" stroke="currentColor" strokeOpacity="0.14" strokeWidth="1" />
          <circle cx="612" cy="436" r="3" className="app-ambient-indicator" fill="#22c55e" fillOpacity="0.5" />
          <circle cx="624" cy="436" r="3" fill="currentColor" fillOpacity="0.15" />
        </g>

        {/* —— Warehouse bag stacks (left / centre) —— */}
        <g className="app-ambient-bags">
          <BagStack x={80} y={520} w={52} h={72} rows={4} opacity={1} />
          <BagStack x={220} y={540} w={48} h={68} rows={3} opacity={0.92} />
          <BagStack x={340} y={510} w={50} h={70} rows={5} opacity={0.88} />
          <BagStack x={470} y={530} w={46} h={66} rows={3} opacity={0.85} />

          {/* foreground bags with label */}
          <g className="app-ambient-bags-front">
            <path
              d="M560 600V420l54-22 54 22v180H560z"
              fill="url(#woven)"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeOpacity="0.32"
            />
            <path d="M614 398l54 22-54 22-54-22z" fill="currentColor" fillOpacity="0.12" />
            <text x="582" y="510" fontFamily="Inter,Segoe UI,sans-serif" fontSize="18" fontWeight="700" fill="currentColor" fillOpacity="0.22">
              50 KG
            </text>

            <path
              d="M680 600V430l50-20 50 20v170H680z"
              fill="url(#woven)"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeOpacity="0.28"
            />
            <text x="698" y="515" fontFamily="Inter,Segoe UI,sans-serif" fontSize="16" fontWeight="700" fill="currentColor" fillOpacity="0.18">
              50 KG
            </text>
          </g>
        </g>

        {/* dust / light motes */}
        <circle className="app-ambient-mote app-ambient-mote--1" cx="400" cy="300" r="2" fill="currentColor" fillOpacity="0.2" />
        <circle className="app-ambient-mote app-ambient-mote--2" cx="520" cy="240" r="1.5" fill="currentColor" fillOpacity="0.16" />
        <circle className="app-ambient-mote app-ambient-mote--3" cx="760" cy="200" r="2" fill="currentColor" fillOpacity="0.14" />
      </svg>
    </div>
  );
}
