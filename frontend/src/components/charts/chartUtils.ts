export const COLORS = {
  positive: '#22c55e',
  negative: '#ef4444',
  notMentioned: '#6b7280',
  primary: '#3b82f6',
};

export const TOOLTIP_STYLE = {
  background: '#111827',
  border: '1px solid #374151',
  color: '#f9fafb',
  borderRadius: '8px',
};

export function formatAspect(aspect: string) {
  return aspect.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}
