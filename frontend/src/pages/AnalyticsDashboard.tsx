import { type FC, useMemo } from 'react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useAnalyticsSummary } from '@/hooks/useAnalytics';
import { useTrackersList } from '@/hooks/useTrackers';
import type { TrackedProduct } from '@/services/api';

interface AnalyticsDashboardProps {
  trackingData: TrackedProduct[];
}

interface ChartPoint {
  date: string;
  price: number;
}

const normalizeHistory = (trackingData: TrackedProduct[]): ChartPoint[] => {
  const allPoints: ChartPoint[] = [];

  trackingData.forEach((product) => {
    product.price_histories.forEach((history) => {
      if (typeof history.scraped_at !== 'string' || typeof history.price !== 'number') {
        return;
      }

      allPoints.push({
        date: new Date(history.scraped_at).toLocaleDateString('en-IN', {
          month: 'short',
          day: 'numeric',
        }),
        price: history.price,
      });
    });
  });

  const uniqueByDate = new Map<string, ChartPoint>();

  allPoints.forEach((point) => {
    const existing = uniqueByDate.get(point.date);
    if (!existing || point.price > existing.price) {
      uniqueByDate.set(point.date, point);
    }
  });

  return Array.from(uniqueByDate.values()).sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
};

const tooltipFormatter = (value: number | string) => `Rs. ${value}`;

export const AnalyticsPage: FC = () => {
  const { data: trackers = [], isLoading, error } = useTrackersList();

  if (isLoading) {
    return <div className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6 text-slate-400">Loading analytics...</div>;
  }

  if (error) {
    return <div className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6 text-rose-300">Unable to load analytics right now.</div>;
  }

  return <AnalyticsDashboard trackingData={trackers} />;
};

export const AnalyticsDashboard: FC<AnalyticsDashboardProps> = ({ trackingData }) => {
  const { data: analytics } = useAnalyticsSummary();
  const chartData = useMemo(() => normalizeHistory(trackingData), [trackingData]);
  const latestPrice = chartData[chartData.length - 1]?.price ?? 0;
  const startPrice = chartData[0]?.price ?? 0;
  const delta = chartData.length > 1 ? latestPrice - startPrice : 0;
  const deltaLabel = delta === 0 ? 'steady' : delta > 0 ? 'up' : 'down';
  const trendText = delta === 0 ? 'Price movement is flat right now.' : `Price is ${deltaLabel} by Rs. ${Math.abs(delta).toFixed(2)}.`;

  return (
    <div className="min-h-screen bg-slate-950 px-6 py-8 text-slate-100">
      <div className="mx-auto max-w-7xl space-y-8">
        <header className="rounded-3xl border border-slate-800 bg-slate-900/80 p-8 shadow-2xl shadow-black/20">
          <p className="text-sm font-semibold uppercase tracking-[0.35em] text-slate-400">Analytics</p>
          <h1 className="mt-3 text-3xl font-semibold text-white">Realtime price movement</h1>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-400">
            Track your most important product pricing history in a single view and monitor live threshold events as they occur.
          </p>
        </header>

        <section className="grid gap-6 xl:grid-cols-[2fr_1fr]">
          <div className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6 shadow-xl shadow-black/20">
            <div className="mb-6 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-sm font-semibold uppercase tracking-[0.32em] text-slate-400">Price Trend</p>
                <h2 className="text-2xl font-semibold text-white">Latest product history</h2>
              </div>
              <div className="rounded-2xl bg-slate-950/70 px-4 py-3 text-sm text-slate-300">
                {chartData.length} data points
              </div>
            </div>

            {chartData.length === 0 ? (
              <div className="flex h-[320px] items-center justify-center rounded-2xl border border-dashed border-slate-700 bg-slate-950/60 p-6 text-center text-sm text-slate-400">
                <div>
                  <p className="font-medium text-white">No price history yet</p>
                  <p className="mt-2">Add a tracker and let the scraper collect enough observations to build a trend chart.</p>
                </div>
              </div>
            ) : (
              <div className="h-[420px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData} margin={{ top: 20, right: 24, left: 0, bottom: 12 }}>
                    <CartesianGrid stroke="#334155" strokeDasharray="3 3" />
                    <XAxis dataKey="date" stroke="#94a3b8" />
                    <YAxis stroke="#94a3b8" tickFormatter={(value) => `Rs. ${value}`} />
                    <Tooltip formatter={tooltipFormatter} labelStyle={{ color: '#f8fafc' }} />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey="price"
                      name="Price"
                      stroke="#10b981"
                      strokeWidth={3}
                      dot={{ r: 3, fill: '#10b981' }}
                      activeDot={{ r: 6, fill: '#f8fafc' }}
                      animationDuration={800}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          <div className="space-y-6">
            <div className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6 shadow-xl shadow-black/20">
              <p className="text-sm font-semibold uppercase tracking-[0.32em] text-slate-400">Performance summary</p>
              <h3 className="mt-3 text-xl font-semibold text-white">Market velocity</h3>
              <p className="mt-3 text-sm leading-7 text-slate-400">
                {analytics ? `${analytics.active_trackers} active trackers are feeding the latest price signals.` : 'The dashboard aggregates the latest tracked product history and adapts the chart for threshold alerts.'}
              </p>
              <p className="mt-3 text-sm leading-7 text-emerald-300">{trendText}</p>
            </div>

            <div className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6 shadow-xl shadow-black/20">
              <p className="text-sm font-semibold uppercase tracking-[0.32em] text-slate-400">Quick metrics</p>
              <div className="mt-5 grid gap-4">
                <div className="rounded-2xl border border-slate-800 bg-slate-950/80 p-4">
                  <p className="text-sm text-slate-400">Most recent price</p>
                  <p className="mt-2 text-2xl font-semibold text-white">Rs. {latestPrice.toFixed(2)}</p>
                </div>
                <div className="rounded-2xl border border-slate-800 bg-slate-950/80 p-4">
                  <p className="text-sm text-slate-400">Tracked products</p>
                  <p className="mt-2 text-2xl font-semibold text-white">{analytics?.tracker_count ?? trackingData.length}</p>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};
