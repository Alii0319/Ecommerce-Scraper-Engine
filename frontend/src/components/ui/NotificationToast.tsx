import { Bell } from 'lucide-react';
import type { AlertItem } from '@/hooks/useWebSocketAlerts';

interface NotificationToastProps {
  alerts: AlertItem[];
  onDismiss: (id: string) => void;
}

export const NotificationToast = ({ alerts, onDismiss }: NotificationToastProps) => {
  if (alerts.length === 0) {
    return null;
  }

  return (
    <div className="pointer-events-none fixed right-4 top-4 z-50 flex flex-col gap-3">
      {alerts.map((alert) => (
        <div
          key={alert.id}
          className="pointer-events-auto overflow-hidden rounded-3xl border border-emerald-500/20 bg-slate-950/95 shadow-2xl shadow-black/40"
        >
          <div className="flex items-center justify-between gap-3 px-4 py-3">
            <div className="flex items-center gap-2">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-emerald-500/10 text-emerald-300">
                <Bell size={18} />
              </div>
              <div>
                <p className="text-sm font-semibold text-white">{alert.productName}</p>
                <p className="text-xs text-slate-400">Dropped to Rs. {alert.currentPrice}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => onDismiss(alert.id)}
              className="rounded-full border border-slate-700 bg-slate-950/90 px-2 py-1 text-xs text-slate-400 transition hover:border-emerald-500 hover:text-emerald-300"
            >
              Dismiss
            </button>
          </div>
          <div className="flex items-center justify-between border-t border-slate-800 px-4 py-3 text-xs text-slate-500">
            <span className="inline-flex items-center gap-2">
              <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-emerald-400" />
              Real-time alert
            </span>
            <span>{alert.timestamp}</span>
          </div>
        </div>
      ))}
    </div>
  );
};
