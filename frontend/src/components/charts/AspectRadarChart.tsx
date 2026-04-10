import {
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Tooltip,
} from 'recharts';
import type { ChartDistribution } from '../../types/report';
import { COLORS, TOOLTIP_STYLE, formatAspect } from './chartUtils';
import { ChartEmptyState } from './ChartEmptyState';

interface AspectRadarChartProps {
  distributions: ChartDistribution[];
}

export function AspectRadarChart({ distributions }: AspectRadarChartProps) {
  const allZero = distributions.every(d => d.positive + d.negative === 0);
  if (allZero) return <ChartEmptyState message="No positivity data to display" />;

  const data = distributions.map(d => {
    const mentioned = d.positive + d.negative;
    const positivityScore = mentioned > 0 ? (d.positive / mentioned) * 100 : 0;
    return {
      aspect: formatAspect(d.aspect),
      score: Math.round(positivityScore),
    };
  });

  return (
    <ResponsiveContainer width="100%" height={300}>
      <RadarChart data={data}>
        <PolarGrid stroke="#374151" />
        <PolarAngleAxis dataKey="aspect" tick={{ fontSize: 11, fill: '#9ca3af' }} />
        <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fontSize: 10, fill: '#6b7280' }} />
        <Tooltip
          formatter={(value) => `${value}%`}
          contentStyle={TOOLTIP_STYLE}
        />
        <Radar
          name="Positivity Score"
          dataKey="score"
          stroke={COLORS.primary}
          fill={COLORS.primary}
          fillOpacity={0.3}
        />
      </RadarChart>
    </ResponsiveContainer>
  );
}
