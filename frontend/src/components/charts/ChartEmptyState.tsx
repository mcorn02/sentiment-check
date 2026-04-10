import { BarChart3 } from 'lucide-react';

interface ChartEmptyStateProps {
  message?: string;
}

export function ChartEmptyState({ message = 'No sentiment data available' }: ChartEmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center h-[250px] text-gray-500">
      <BarChart3 className="w-10 h-10 mb-3 text-gray-600" />
      <p className="text-sm">{message}</p>
    </div>
  );
}
