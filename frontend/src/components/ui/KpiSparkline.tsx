import { Area, AreaChart, ResponsiveContainer } from "recharts";

type Props = {
  data: Array<{ x: number | string; y: number }>;
  color?: string;
  gradientId?: string;
};

export default function KpiSparkline({ data, color = "#6366f1", gradientId = "spark" }: Props) {
  if (!data?.length) return null;
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.4} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <Area
          type="monotone"
          dataKey="y"
          stroke={color}
          strokeWidth={2}
          fill={`url(#${gradientId})`}
          isAnimationActive
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
