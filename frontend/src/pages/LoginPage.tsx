import { useMemo, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, LockKeyhole, Mail } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { extractErrorMessage } from '@/services/api';

interface LoginFormState {
  email: string;
  password: string;
}

const initialState: LoginFormState = {
  email: '',
  password: '',
};

export const LoginPage = () => {
  const navigate = useNavigate();
  const { login, isLoading } = useAuth();
  const [formState, setFormState] = useState<LoginFormState>(initialState);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const canSubmit = useMemo(() => formState.email.trim().length > 0 && formState.password.length > 0, [formState.email, formState.password]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMessage(null);

    try {
      await login(formState.email.trim(), formState.password);
      navigate('/dashboard/trackers', { replace: true });
    } catch (error) {
      setErrorMessage(extractErrorMessage(error));
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4 py-12 text-slate-100">
      <div className="w-full max-w-md rounded-3xl border border-slate-800 bg-slate-900/90 p-8 shadow-2xl shadow-black/40">
        <div className="mb-8 text-center">
          <p className="text-sm font-semibold uppercase tracking-[0.35em] text-slate-400">Secure Access</p>
          <h1 className="mt-3 text-3xl font-semibold text-white">Welcome back</h1>
          <p className="mt-3 text-sm leading-6 text-slate-400">
            Sign in to manage your tracking inventory and price monitoring workflows.
          </p>
        </div>

        {errorMessage ? (
          <div className="mb-5 rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
            {errorMessage}
          </div>
        ) : null}

        <form className="space-y-5" onSubmit={handleSubmit}>
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-300" htmlFor="email">
              Email address
            </label>
            <div className="flex items-center gap-3 rounded-2xl border border-slate-700 bg-slate-950/70 px-3 py-3">
              <Mail size={18} className="text-slate-500" />
              <input
                id="email"
                type="email"
                autoComplete="email"
                value={formState.email}
                onChange={(event) => setFormState((current) => ({ ...current, email: event.target.value }))}
                className="w-full bg-transparent text-sm text-white outline-none"
                placeholder="name@example.com"
                disabled={isLoading}
                required
              />
            </div>
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-slate-300" htmlFor="password">
              Password
            </label>
            <div className="flex items-center gap-3 rounded-2xl border border-slate-700 bg-slate-950/70 px-3 py-3">
              <LockKeyhole size={18} className="text-slate-500" />
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={formState.password}
                onChange={(event) => setFormState((current) => ({ ...current, password: event.target.value }))}
                className="w-full bg-transparent text-sm text-white outline-none"
                placeholder="Enter your password"
                disabled={isLoading}
                required
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={!canSubmit || isLoading}
            className="flex w-full items-center justify-center gap-2 rounded-2xl bg-emerald-500 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-400"
          >
            {isLoading ? 'Signing in...' : 'Sign in'}
            <ArrowRight size={16} />
          </button>
        </form>

        <div className="mt-6 text-center text-sm text-slate-400">
          New to the platform?{' '}
          <a className="font-medium text-emerald-300 transition hover:text-emerald-200" href="/register">
            Create account
          </a>
        </div>
      </div>
    </div>
  );
};
