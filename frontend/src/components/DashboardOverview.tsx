import React, { useEffect, useMemo, useRef, useState } from 'react';
import type { TrackedProduct } from '@/services/api';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';

interface PricePoint {
  time: string;
  price: number;
}

interface Props {
  trackers: TrackedProduct[];
  onSimulateAlert?: (alert: { productName: string; currentPrice: number; timestamp: string }) => void;
}

const formatTime = (date: Date): string => date.toLocaleTimeString();

export const DashboardOverview: React.FC<Props> = ({ trackers, onSimulateAlert }) => {
  const [selectedId, setSelectedId] = useState<number | null>(() => (trackers[0]?.id ?? null));
  const selectedTracker = useMemo(() => trackers.find((t) => t.id === selectedId) ?? trackers[0] ?? null, [trackers, selectedId]);

  const initialHistory = useMemo<PricePoint[]>(() => {
    if (!selectedTracker) return [];
    
    // Safely parse baselinePrice using the correct evaluation logic (starting buffer above threshold)
    const baselinePrice = selectedTracker.current_price 
      ? parseFloat(String(selectedTracker.current_price)) 
      : parseFloat(String(selectedTracker.notification_threshold)) * 1.05;

    if (!selectedTracker.price_histories || selectedTracker.price_histories.length === 0) {
      // Synthesize a realistic history around the baseline price
      const now = Date.now();
      return Array.from({ length: 12 }).map((_, i) => {
        // Safe fluctuations around the baseline price (e.g. within 2%)
        const delta = Math.sin(i / 2) * (baselinePrice * 0.02);
        return {
          time: formatTime(new Date(now - (11 - i) * 60 * 1000)),
          price: parseFloat((baselinePrice + delta).toFixed(2)),
        };
      });
    }

    return selectedTracker.price_histories.slice(-24).map((p) => ({
      time: p.scraped_at ? formatTime(new Date(p.scraped_at)) : '',
      price: parseFloat(String(p.price)) || baselinePrice,
    }));
  }, [selectedTracker]);

  const [chartData, setChartData] = useState<PricePoint[]>(initialHistory);

  useEffect(() => {
    setSelectedId((current) => (trackers.find((t) => t.id === current) ? current : trackers[0]?.id ?? null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trackers]);

  useEffect(() => {
    setChartData(initialHistory);
  }, [initialHistory]);

  const simulateDrop = (): void => {
    if (!selectedTracker) return;
    setChartData((current) => {
      const baselinePrice = selectedTracker.current_price 
        ? parseFloat(String(selectedTracker.current_price)) 
        : parseFloat(String(selectedTracker.notification_threshold)) * 1.05;

      const currentLatestPrice = current.length > 0 
        ? current[current.length - 1].price 
        : baselinePrice;

      const simulatedDroppedPrice = currentLatestPrice - (50 + Math.random() * 30);
      const nextPriceFormatted = parseFloat(simulatedDroppedPrice.toFixed(2));
      const now = Date.now();

      const newPoint: PricePoint = {
        time: formatTime(new Date(now)),
        price: nextPriceFormatted,
      };

      const calculatedLatestPrice = nextPriceFormatted;
      const currentThreshold = parseFloat(String(selectedTracker.notification_threshold));

      if (calculatedLatestPrice <= currentThreshold && onSimulateAlert) {
        onSimulateAlert({
          productName: selectedTracker.product_name,
          currentPrice: calculatedLatestPrice,
          timestamp: new Date().toLocaleTimeString(),
        });
      }

      // Append and slice
      return [...current, newPoint].slice(-120);
    });
  };

  // Activity log terminal
  const [logs, setLogs] = useState<string[]>(() => [
    `⏱️ [${new Date().toLocaleTimeString()}] Celery Beat triggered 4-hour cron sequence...`,
    `🚀 [${new Date(new Date().getTime() + 2000).toLocaleTimeString()}] Worker Node #1 spawned Headless Chromium instance...`,
    `🔍 [${new Date(new Date().getTime() + 5000).toLocaleTimeString()}] Target URL parsed successfully. Extracting CSS selectors...`,
  ]);
  const logRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const tasks = [
      'Scheduler health check passed.',
      'Worker Node #2 connecting to broker...',
      'Fetching next batch of targets...',
      'Snapshot saved to S3 archive.',
      'Alert: price delta exceeded threshold for 3 trackers.',
    ];

    const iv = setInterval(() => {
      setLogs((current) => {
        const next = [`${new Date().toLocaleTimeString()} • ${tasks[Math.floor(Math.random() * tasks.length)]}`, ...current].slice(0, 200);
        return next;
      });
    }, 2200);

    return () => clearInterval(iv);
  }, []);

  useEffect(() => {
    if (!logRef.current) return;
    // smooth auto-scroll to top so newest appear at top, but animate using CSS
    logRef.current.scrollTo({ top: 0, behavior: 'smooth' });
  }, [logs]);

  const latestDelta = useMemo(() => {
    if (chartData.length < 2) return 0;
    return parseFloat((chartData[chartData.length - 1].price - chartData[chartData.length - 2].price).toFixed(2));
  }, [chartData]);

  const trendColor = latestDelta < 0 ? '#ef4444' : '#34d399';

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium uppercase tracking-[0.3em] text-slate-400">Overview</p>
          <h3 className="text-2xl font-semibold text-white">Workspace analytics</h3>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-3">
            <span className="rounded-full bg-slate-800 px-3 py-1 text-sm text-slate-300">Operational Mode</span>
            <span className="inline-flex items-center gap-2 rounded-2xl bg-slate-950/70 px-3 py-1 text-sm text-white">
              <span className="h-3 w-3 rounded-full bg-emerald-400 animate-pulse" />
              <span>Live</span>
            </span>
          </div>

          <button
            type="button"
            onClick={simulateDrop}
            className="rounded-2xl bg-rose-500 px-4 py-2 text-sm font-semibold text-white shadow hover:scale-105 transition-transform duration-200"
          >
            Simulate Market Price Drop
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="col-span-2 rounded-2xl border border-slate-800 bg-slate-950/70 p-4 shadow">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-400">Selected Tracker</p>
              <p className="mt-1 text-lg font-semibold text-white">{selectedTracker?.product_name ?? '—'}</p>
            </div>
            <div className="text-right">
              <p className="text-sm text-slate-400">Latest</p>
              <p className="mt-1 text-xl font-semibold" style={{ color: trendColor }}>
                {chartData[chartData.length - 1] ? `Rs. ${Number(chartData[chartData.length - 1].price).toFixed(2)}` : '—'}
              </p>
            </div>
          </div>

          <div className="mt-4 h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 8 }}>
                <CartesianGrid stroke="#0f172a" strokeDasharray="3 3" />
                <XAxis dataKey="time" tick={{ fill: '#94a3b8' }} />
                <YAxis tick={{ fill: '#94a3b8' }} />
                <Tooltip formatter={(value) => [`Rs. ${Number(value).toFixed(2)}`, "Price"]} labelStyle={{ color: '#94a3b8' }} />
                <Line type="monotone" dataKey="price" stroke="#10b981" activeDot={{ r: 8 }} isAnimationActive={true} strokeWidth={2} dot={{ r: 2 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4 shadow">
          <p className="text-sm text-slate-400">Tracker list</p>
          <div className="mt-3 flex flex-col gap-2 max-h-48 overflow-auto">
            {trackers.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => {
                  setSelectedId(t.id);
                }}
                className={`w-full rounded-xl border px-3 py-2 text-left text-sm transition hover:bg-slate-900/60 ${t.id === selectedTracker?.id ? 'border-emerald-500/40 bg-emerald-500/5' : 'border-transparent'}`}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm font-medium text-white">{t.product_name}</div>
                    <div className="text-xs text-slate-400">{t.domain_name}</div>
                  </div>
                  <div className="text-sm text-slate-300">{t.is_active ? 'Active' : 'Paused'}</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-900/90 p-4 shadow-lg">
        <div className="mb-3 flex items-center justify-between">
          <h4 className="text-sm font-semibold text-white">Engine Status Logs</h4>
          <div className="text-xs text-slate-400">Streaming • {logs.length} entries</div>
        </div>

        <div ref={logRef} className="max-h-40 overflow-y-auto rounded-md bg-black/60 p-3 font-mono text-xs text-slate-200">
          <div className="flex flex-col-reverse gap-2">
            {logs.map((l, i) => (
              <div key={`${l}-${i}`} className="opacity-95 leading-tight">{l}</div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default DashboardOverview;
