import type { ChartDistribution } from '../../types/report';
import { COLORS, formatAspect } from './chartUtils';
import { ChartEmptyState } from './ChartEmptyState';

interface AspectSentimentGridProps {
  distributions: ChartDistribution[];
}

export function AspectSentimentGrid({ distributions }: AspectSentimentGridProps) {
  const allZero = distributions.every(d => d.positive + d.negative === 0);
  if (allZero) return <ChartEmptyState />;

  return (
    <div className="space-y-3">
      {distributions.map(d => {
        const mentioned = d.positive + d.negative;
        const posRatio = mentioned > 0 ? (d.positive / mentioned) * 100 : 0;
        const negRatio = mentioned > 0 ? (d.negative / mentioned) * 100 : 0;

        return (
          <div key={d.aspect} className="space-y-1">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-300 font-medium">{formatAspect(d.aspect)}</span>
              <span className="text-xs text-gray-500">{mentioned} mentions</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="flex-1 h-3 bg-gray-800 rounded-full overflow-hidden flex">
                {posRatio > 0 && (
                  <div
                    className="h-full rounded-l-full"
                    style={{ width: `${posRatio}%`, backgroundColor: COLORS.positive }}
                  />
                )}
                {negRatio > 0 && (
                  <div
                    className="h-full"
                    style={{
                      width: `${negRatio}%`,
                      backgroundColor: COLORS.negative,
                      borderRadius: posRatio === 0 ? '9999px 0 0 9999px' : '0',
                    }}
                  />
                )}
              </div>
              <span className="text-xs text-gray-400 w-12 text-right">
                {mentioned > 0 ? `${Math.round(posRatio)}%` : '—'}
              </span>
            </div>
          </div>
        );
      })}
      <div className="flex items-center gap-4 pt-2 text-xs text-gray-500">
        <span className="flex items-center gap-1">
          <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: COLORS.positive }} />
          Positive
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: COLORS.negative }} />
          Negative
        </span>
        <span className="ml-auto">% shown is positive of mentioned</span>
      </div>
    </div>
  );
}
