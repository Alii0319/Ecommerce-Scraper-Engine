import { useState } from 'react';
import { useAuth } from '@/context/AuthContext';

export const SettingsPage = () => {
  const { user, isLoading } = useAuth();
  
  // Local state hook initialized directly from localStorage setting
  const [wsEnabled, setWsEnabled] = useState(localStorage.getItem('app_settings_ws_enabled') !== 'false');

  if (isLoading) {
    return <div className="p-8 text-slate-100">Loading settings...</div>;
  }

  return (
    <div className="p-8 text-slate-100">
      <h2 className="mb-4 text-2xl font-semibold">Settings</h2>

      <section className="mb-8">
        <h3 className="mb-2 text-lg font-medium">User Meta</h3>
        <div className="max-w-md">
          <label className="mb-2 block text-sm font-medium text-slate-300">Email</label>
          <input
            type="email"
            value={user?.email ?? ''}
            placeholder={user?.email ?? 'email@example.com'}
            readOnly
            disabled
            aria-disabled
            className="w-full rounded-2xl border border-slate-700 bg-slate-950/70 px-3 py-3 text-sm text-slate-400 outline-none cursor-not-allowed"
          />
        </div>
      </section>

      <section>
        <h3 className="mb-2 text-lg font-medium">System Monitoring Configs</h3>
        <div className="flex items-center gap-4">
          <div>
            <p className="mb-1 text-sm text-slate-300">Real-Time WebSocket Streams Dashboard Alerts</p>
            <p className="mb-2 text-xs text-slate-400">Toggle to receive real-time alerts in the dashboard.</p>
            <label className="inline-flex items-center gap-3">
              <input
                type="checkbox"
                checked={wsEnabled}
                onChange={() => {
                  const nextVal = !wsEnabled;
                  setWsEnabled(nextVal);
                  localStorage.setItem('app_settings_ws_enabled', String(nextVal));
                }}
                className="h-5 w-5 rounded border border-slate-700 bg-slate-900 text-emerald-500"
              />
              <span className="text-sm text-slate-200">Enabled</span>
            </label>
          </div>
        </div>
      </section>
    </div>
  );
};

export default SettingsPage;
