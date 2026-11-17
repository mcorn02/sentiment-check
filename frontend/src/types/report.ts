export interface SentimentDistribution {
  positive: { count: number; pct: number };
  negative: { count: number; pct: number };
  not_mentioned: { count: number; pct: number };
}

export interface TopQuote {
  sentence: string;
  review: number;
}

export interface AspectReport {
  name: string;
  distribution: SentimentDistribution;
  narrative: string;
  top_quotes: TopQuote[];
}

export interface ChartDistribution {
  aspect: string;
  positive: number;
  negative: number;
  not_mentioned: number;
  positive_pct: number;
  negative_pct: number;
  not_mentioned_pct: number;
}

export interface Insight {
  type: 'risk' | 'strength' | 'trend' | 'opportunity';
  severity: 'high' | 'medium' | 'low';
  title: string;
  description: string;
}

export interface ReportData {
  report_id: string;
  overall_summary: string;
  title: string;
  /** @deprecated Use title instead */
  n_reviews: number;
  aspects: AspectReport[];
}

export type PipelineStage = 'idle' | 'parsing' | 'scraping' | 'analyzing' | 'generating' | 'done' | 'error';

export interface StageEvent {
  stage: PipelineStage;
  message?: string;
  progress?: number;
  total?: number;
  title?: string;
  /** @deprecated Use title instead */
}

export interface DomainConfig {
  id: string;
  name: string;
  aspects: string[];
  description: string | null;
  is_preset: boolean;
}
