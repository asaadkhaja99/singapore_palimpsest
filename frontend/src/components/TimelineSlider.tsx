"use client";

export function TimelineSlider({
  eras,
  currentEra,
  onChange,
}: {
  eras: number[];
  currentEra: number;
  onChange: (era: number) => void;
}) {
  const index = Math.max(0, eras.indexOf(currentEra));
  return (
    <div className="timeline glass-panel">
      <input
        aria-label="Timeline"
        type="range"
        min={0}
        max={Math.max(0, eras.length - 1)}
        step={1}
        value={index}
        onChange={(event) => onChange(eras[Number(event.target.value)])}
      />
      <div className="timeline-labels">
        {eras.map((era) => (
          <span key={era}>{era}</span>
        ))}
      </div>
    </div>
  );
}
