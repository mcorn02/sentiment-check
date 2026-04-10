import type { Insight } from '../../types/report';
import { Card, CardBody } from '../ui/Card';

interface InsightsPanelProps {
  insights: Insight[];
}

const TYPE_CONFIG = {
  risk: { border: 'border-l-red-500', label: 'Risk', labelColor: 'text-red-400' },
  strength: { border: 'border-l-green-500', label: 'Strength', labelColor: 'text-green-400' },
  trend: { border: 'border-l-yellow-500', label: 'Trend', labelColor: 'text-yellow-400' },
  opportunity: { border: 'border-l-blue-500', label: 'Opportunity', labelColor: 'text-blue-400' },
};

const SEVERITY_BADGE = {
  high: 'bg-red-950 text-red-300 border-red-800',
  medium: 'bg-yellow-950 text-yellow-300 border-yellow-800',
  low: 'bg-gray-800 text-gray-300 border-gray-700',
};

export function InsightsPanel({ insights }: InsightsPanelProps) {
  if (!insights || insights.length === 0) return null;

  return (
    <div className="space-y-3">
      <h2 className="text-lg font-semibold text-white">Key Insights</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {insights.map((insight, i) => {
          const config = TYPE_CONFIG[insight.type] ?? TYPE_CONFIG.trend;
          const severity = SEVERITY_BADGE[insight.severity] ?? SEVERITY_BADGE.low;

          return (
            <Card key={i} className={`border-l-4 ${config.border}`}>
              <CardBody className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className={`text-xs font-medium uppercase tracking-wide ${config.labelColor}`}>
                    {config.label}
                  </span>
                  <span className={`text-xs px-2 py-0.5 rounded-full border ${severity}`}>
                    {insight.severity}
                  </span>
                </div>
                <h3 className="text-sm font-semibold text-white">{insight.title}</h3>
                <p className="text-sm text-gray-400 leading-relaxed">{insight.description}</p>
              </CardBody>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
