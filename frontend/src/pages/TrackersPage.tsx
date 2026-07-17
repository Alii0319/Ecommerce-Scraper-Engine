import { useMemo, useState, type FormEvent } from 'react';
import DashboardOverview from '@/components/DashboardOverview';
import { PlusCircle, Trash2 } from 'lucide-react';
import { useCreateTracker, useDeleteTracker, useTrackersList } from '@/hooks/useTrackers';
import { useWebSocketAlerts } from '@/hooks/useWebSocketAlerts';
import { NotificationToast } from '@/components/ui/NotificationToast';
import { useAnalyticsSummary } from '@/hooks/useAnalytics';

interface TrackerFormState {
  product_name: string;
  target_url: string;
  notification_threshold: string;
}

const initialFormState: TrackerFormState = {
  product_name: '',
  target_url: '',
  notification_threshold: '',
};

export const TrackersPage = () => {
  const { data: trackers = [], isLoading, error } = useTrackersList();
  const { data: analytics } = useAnalyticsSummary();
  const createTracker = useCreateTracker();
  const deleteTracker = useDeleteTracker();
  const { notifications, acknowledgeAlert, triggerLocalAlert } = useWebSocketAlerts();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [formState, setFormState] = useState<TrackerFormState>(initialFormState);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const totalActive = useMemo(() => trackers.filter((tracker) => tracker.is_active).length, [trackers]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitError(null);

    const product_name = formState.product_name.trim();
    const target_url = formState.target_url.trim();
    const notification_threshold = Number(formState.notification_threshold);

    // Client-side validation to avoid server 400s
    if (!product_name) {
      setSubmitError('Product name is required.');
      return;
    }
    if (product_name.length > 255) {
      setSubmitError('Product name must be 255 characters or fewer.');
      return;
    }

    try {
      // validate URL
      try {
        // eslint-disable-next-line no-new
        new URL(target_url);
      } catch {
        setSubmitError('Target URL is invalid. Use a fully-qualified URL (https://...).');
        return;
      }

      if (Number.isNaN(notification_threshold)) {
        setSubmitError('Notification threshold must be a number.');
        return;
      }

      // DecimalField(max_digits=10, decimal_places=2) max integer digits 8 -> max value ~ 99999999.99
      if (notification_threshold < 0 || notification_threshold > 99999999.99) {
        setSubmitError('Notification threshold is out of allowed range.');
        return;
      }

      const payload = {
        product_name,
        target_url,
        notification_threshold,
        is_active: true,
      };

      await createTracker.mutateAsync(payload);
      setFormState(initialFormState);
      setIsModalOpen(false);
    } catch (err: unknown) {
      // Try to surface server-provided error details for debugging
      // If axios error, it may contain response.data
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const anyErr = err as any;
      if (anyErr?.response?.data) {
        setSubmitError(typeof anyErr.response.data === 'string' ? anyErr.response.data : JSON.stringify(anyErr.response.data));
      } else if (anyErr?.message) {
        setSubmitError(anyErr.message);
      } else {
        setSubmitError('Failed to create tracker.');
      }
      // also log to console for deeper inspection
      // eslint-disable-next-line no-console
      console.error('Create tracker error:', anyErr);
    }
  };

  return (
    <div className="space-y-6 rounded-3xl border border-slate-800 bg-slate-900/80 p-6 shadow-xl shadow-black/20">
      <NotificationToast alerts={notifications} onDismiss={acknowledgeAlert} />
      <DashboardOverview trackers={trackers} onSimulateAlert={triggerLocalAlert} />
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-sm font-medium uppercase tracking-[0.3em] text-slate-400">Tracker Inventory</p>
          <h2 className="text-2xl font-semibold text-white">Live product watchlist</h2>
        </div>
        <button
          type="button"
          onClick={() => setIsModalOpen(true)}
          className="inline-flex items-center justify-center gap-2 rounded-2xl border border-emerald-500/40 bg-emerald-500/10 px-4 py-3 text-sm font-medium text-emerald-300 transition hover:bg-emerald-500/20"
        >
          <PlusCircle size={16} />
          Add tracker
        </button>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-2xl border border-slate-800 bg-slate-950/80 p-4">
          <p className="text-sm text-slate-400">Active trackers</p>
          <p className="mt-2 text-2xl font-semibold text-white">{analytics?.active_trackers ?? totalActive}</p>
        </div>
        <div className="rounded-2xl border border-slate-800 bg-slate-950/80 p-4">
          <p className="text-sm text-slate-400">Total listed</p>
          <p className="mt-2 text-2xl font-semibold text-white">{analytics?.tracker_count ?? trackers.length}</p>
        </div>
        <div className="rounded-2xl border border-slate-800 bg-slate-950/80 p-4">
          <p className="text-sm text-slate-400">History points</p>
          <p className="mt-2 text-2xl font-semibold text-emerald-300">{analytics?.history_points ?? 0}</p>
        </div>
      </div>

      {!isLoading && !error && trackers.length === 0 && (
        <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-950/60 p-6 text-center text-sm text-slate-400">
          <p className="font-medium text-white">No trackers yet</p>
          <p className="mt-2">Create your first price watch to start collecting price history and alerts.</p>
        </div>
      )}

      <div className="overflow-hidden rounded-2xl border border-slate-800">
        <table className="min-w-full divide-y divide-slate-800 text-sm">
          <thead className="bg-slate-950/80 text-left text-slate-400">
            <tr>
              <th className="px-4 py-3 font-medium">Product</th>
              <th className="px-4 py-3 font-medium">Domain</th>
              <th className="px-4 py-3 font-medium">Threshold</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800 bg-slate-900/70">
            {isLoading && (
              <tr>
                <td className="px-4 py-6 text-slate-400" colSpan={5}>
                  Loading trackers...
                </td>
              </tr>
            )}

            {!isLoading && error && (
              <tr>
                <td className="px-4 py-6 text-rose-300" colSpan={5}>
                  Unable to load trackers right now.
                </td>
              </tr>
            )}


            {!isLoading && !error && trackers.map((tracker) => (
              <tr key={tracker.id}>
                <td className="px-4 py-3 text-white">{tracker.product_name}</td>
                <td className="px-4 py-3 text-slate-400">{tracker.domain_name}</td>
                <td className="px-4 py-3 text-slate-400">Rs. {Number(tracker.notification_threshold).toFixed(2)}</td>
                <td className="px-4 py-3">
                  <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${tracker.is_active ? 'bg-emerald-500/15 text-emerald-300' : 'bg-slate-800 text-slate-400'}`}>
                    {tracker.is_active ? 'Active' : 'Paused'}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <button
                    type="button"
                    onClick={() => {
                      void deleteTracker.mutateAsync(tracker.id);
                    }}
                    className="rounded-full p-2 text-slate-400 transition hover:bg-slate-800 hover:text-rose-300"
                  >
                    <Trash2 size={16} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 px-4 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-3xl border border-slate-800 bg-slate-900 p-6 shadow-2xl shadow-black/30">
            <div className="mb-5 flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold uppercase tracking-[0.3em] text-slate-400">Create tracker</p>
                <h3 className="text-xl font-semibold text-white">New price watch</h3>
              </div>
              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                className="rounded-full p-2 text-slate-400 transition hover:bg-slate-800 hover:text-white"
              >
                ✕
              </button>
            </div>

            <form className="space-y-4" onSubmit={handleSubmit}>
              {submitError && (
                <div className="mb-3 rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
                  {submitError}
                </div>
              )}
              <div>
                <label className="mb-2 block text-sm font-medium text-slate-300" htmlFor="product_name">
                  Product name
                </label>
                <input
                  id="product_name"
                  className="w-full rounded-2xl border border-slate-700 bg-slate-950/60 px-3 py-3 text-sm text-white outline-none ring-0"
                  value={formState.product_name}
                  onChange={(event) => setFormState((current) => ({ ...current, product_name: event.target.value }))}
                  placeholder="Example: Wireless Headphones"
                />
              </div>

              <div>
                <label className="mb-2 block text-sm font-medium text-slate-300" htmlFor="target_url">
                  Target URL
                </label>
                <input
                  id="target_url"
                  className="w-full rounded-2xl border border-slate-700 bg-slate-950/60 px-3 py-3 text-sm text-white outline-none ring-0"
                  value={formState.target_url}
                  onChange={(event) => setFormState((current) => ({ ...current, target_url: event.target.value }))}
                  placeholder="https://example.com/product"
                />
              </div>

              <div>
                <label className="mb-2 block text-sm font-medium text-slate-300" htmlFor="notification_threshold">
                  Notification threshold
                </label>
                <input
                  id="notification_threshold"
                  type="number"
                  step="0.01"
                  className="w-full rounded-2xl border border-slate-700 bg-slate-950/60 px-3 py-3 text-sm text-white outline-none ring-0"
                  value={formState.notification_threshold}
                  onChange={(event) => setFormState((current) => ({ ...current, notification_threshold: event.target.value }))}
                  placeholder="1500"
                />
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="rounded-2xl border border-slate-700 px-4 py-3 text-sm font-medium text-slate-300 transition hover:bg-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="rounded-2xl bg-emerald-500 px-4 py-3 text-sm font-medium text-slate-950 transition hover:bg-emerald-400"
                >
                  Save tracker
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
