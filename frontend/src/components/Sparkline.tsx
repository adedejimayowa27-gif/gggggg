/**
 * A minimal trend line -- no axes, no labels, just the shape of the
 * data. Used inside MetricCard for a real (not decorative/fabricated)
 * at-a-glance trend, built from actual timeseries values passed in.
 */
interface Props {
  values: number[];
  color: string;
  width?: number;
  height?: number;
}

export default function Sparkline({ values, color, width = 72, height = 28 }: Props) {
  if (values.length < 2) return null;

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  const points = values.map((value, i) => {
    const x = (i / (values.length - 1)) * width;
    const y = height - ((value - min) / range) * height;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  return (
    <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} aria-hidden="true">
      <polyline
        points={points.join(" ")}
        fill="none"
        stroke={color}
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
