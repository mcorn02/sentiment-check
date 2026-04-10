import { useSSE } from '../hooks/useSSE';
import { ReviewInput } from '../components/ReviewInput';
import { ProgressStepper } from '../components/ProgressStepper';
import { SentimentBarChart } from '../components/charts/SentimentBarChart';
import { SentimentPieChart } from '../components/charts/SentimentPieChart';
import { AspectRadarChart } from '../components/charts/AspectRadarChart';
import { ReportCard } from '../components/report/ReportCard';
import { AspectSection } from '../components/report/AspectSection';
import { ReportChat } from '../components/ReportChat';
import { Card, CardHeader, CardBody } from '../components/ui/Card';
import { AlertTriangle, XCircle } from 'lucide-react';

export function ReportPage() {
  const sse = useSSE();

  const showProgress = sse.isRunning || sse.stage === 'done';
  const showCharts = sse.distributions.length > 0;
  const showReport = sse.report !== null;
  const aspects = sse.report?.aspects ?? sse.completedAspects;

  return (
    <div className="min-h-screen bg-gray-950">
      <div className="max-w-6xl mx-auto px-4 py-8 space-y-8">
        {/* Header */}
        <div className="text-center">
          <h1 className="text-3xl font-bold text-white">
            Sentiment Check
          </h1>
          <p className="text-gray-400 mt-1">
            Upload your reviews and get AI-powered sentiment insights by aspect
          </p>
        </div>

        {/* Input Form */}
        <Card>
          <CardBody>
            <ReviewInput onSubmitCSV={sse.startCSVReport} isLoading={sse.isRunning} />
          </CardBody>
        </Card>

        {/* Warning */}
        {sse.warning && (
          <div className="flex items-center gap-2 p-4 bg-yellow-950 border border-yellow-800 rounded-lg text-yellow-300 text-sm">
            <AlertTriangle className="w-5 h-5 shrink-0" />
            {sse.warning}
          </div>
        )}

        {/* Error */}
        {sse.error && (
          <div className="flex items-center gap-2 p-4 bg-red-950 border border-red-800 rounded-lg text-red-300 text-sm">
            <XCircle className="w-5 h-5 shrink-0" />
            {sse.error}
          </div>
        )}

        {/* Progress */}
        {showProgress && (
          <Card>
            <CardBody>
              <ProgressStepper
                stage={sse.stage}
                stageMessage={sse.stageMessage}
                progress={sse.progress}
                total={sse.total}
              />
            </CardBody>
          </Card>
        )}

        {/* ReportCard — overview summary */}
        {showReport && sse.report && (
          <ReportCard
            title={sse.report.title}
            nReviews={sse.report.n_reviews}
            overallSummary={sse.report.overall_summary}
          />
        )}

        {/* Charts */}
        {showCharts && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <h2 className="text-lg font-semibold text-white">
                  Sentiment by Aspect
                </h2>
                <p className="text-sm text-gray-400">Among reviews that mentioned each aspect</p>
              </CardHeader>
              <CardBody>
                <SentimentBarChart distributions={sse.distributions} />
              </CardBody>
            </Card>

            <Card>
              <CardHeader>
                <h2 className="text-lg font-semibold text-white">
                  Overall Sentiment
                </h2>
                <p className="text-sm text-gray-400">Aggregate positive vs. negative across all aspects</p>
              </CardHeader>
              <CardBody>
                <SentimentPieChart distributions={sse.distributions} />
              </CardBody>
            </Card>

            <Card className="lg:col-span-2">
              <CardHeader>
                <h2 className="text-lg font-semibold text-white">
                  Positivity Radar
                </h2>
                <p className="text-sm text-gray-400">
                  Positivity score per aspect (% of mentioned reviews that are positive)
                </p>
              </CardHeader>
              <CardBody>
                <AspectRadarChart distributions={sse.distributions} />
              </CardBody>
            </Card>
          </div>
        )}

        {/* Aspect Cards */}
        {showReport && sse.report && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {aspects.map(aspect => (
              <AspectSection key={aspect.name} aspect={aspect} />
            ))}
          </div>
        )}
      </div>

      {/* Floating chat widget */}
      {showReport && sse.report && (
        <ReportChat
          reportId={sse.report.report_id}
          movieTitle={sse.report.title}
        />
      )}
    </div>
  );
}
