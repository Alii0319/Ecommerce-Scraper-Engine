import { useMemo, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Mail, ShieldCheck, UserRound } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { extractErrorMessage } from '@/services/api';

interface RegisterFormState {
  email: string;
  password: string;
  confirmPassword: string;
  first_name: string;
  last_name: string;
}

const initialState: RegisterFormState = {
  email: '',
  password: '',
  confirmPassword: '',
  first_name: '',
  last_name: '',
};

const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export const RegisterPage = () => {
  const navigate = useNavigate();
  const { register, isLoading } = useAuth();
  const [formState, setFormState] = useState<RegisterFormState>(initialState);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const validationMessage = useMemo(() => {
    if (!formState.email) {
      return null;
    }

    if (!emailRegex.test(formState.email)) {
      return 'Please enter a valid email address.';
    }

    if (formState.password.length < 8) {
      return 'Password must be at least 8 characters long.';
    }

    if (formState.confirmPassword && formState.password !== formState.confirmPassword) {
      return 'Passwords do not match.';
    }

    return null;
  }, [formState.email, formState.password]);

  const canSubmit = useMemo(() => {
    return (
      formState.email.trim().length > 0 &&
      formState.password.length >= 8 &&
      formState.confirmPassword.length >= 8 &&
      emailRegex.test(formState.email) &&
      formState.first_name.trim().length > 0 &&
      formState.last_name.trim().length > 0
    );
  }, [formState]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMessage(null);
    setSuccessMessage(null);

    if (!emailRegex.test(formState.email.trim())) {
      setErrorMessage('Please enter a valid email address.');
      return;
    }

    if (formState.password.length < 8) {
      setErrorMessage('Password must be at least 8 characters long.');
      return;
    }

    if (formState.password !== formState.confirmPassword) {
      setErrorMessage('Passwords do not match.');
      return;
    }

    try {
      await register(formState.email.trim(), formState.password, formState.first_name.trim(), formState.last_name.trim());
      setSuccessMessage('Account created successfully. Redirecting to login...');
      window.setTimeout(() => {
        navigate('/login', { replace: true });
      }, 1200);
    } catch (error) {
      setErrorMessage(extractErrorMessage(error));
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4 py-12 text-slate-100">
      <div className="w-full max-w-xl rounded-3xl border border-slate-800 bg-slate-900/90 p-8 shadow-2xl shadow-black/40">
        <div className="mb-8 text-center">
          <p className="text-sm font-semibold uppercase tracking-[0.35em] text-slate-400">Create Account</p>
          <h1 className="mt-3 text-3xl font-semibold text-white">Join the control center</h1>
          <p className="mt-3 text-sm leading-6 text-slate-400">
            Register your workspace credentials and begin orchestrating tracker operations.
          </p>
        </div>

        {errorMessage ? (
          <div className="mb-5 rounded-2xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
            {errorMessage}
          </div>
        ) : null}

        {successMessage ? (
          <div className="mb-5 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">
            {successMessage}
          </div>
        ) : null}

        <form className="space-y-4" onSubmit={handleSubmit}>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="mb-2 block text-sm font-medium text-slate-300" htmlFor="first_name">
                First name
              </label>
              <div className="flex items-center gap-3 rounded-2xl border border-slate-700 bg-slate-950/70 px-3 py-3">
                <UserRound size={18} className="text-slate-500" />
                <input
                  id="first_name"
                  value={formState.first_name}
                  onChange={(event) => setFormState((current) => ({ ...current, first_name: event.target.value }))}
                  className="w-full bg-transparent text-sm text-white outline-none"
                  disabled={isLoading}
                  placeholder="First name"
                  required
                />
              </div>
            </div>

            <div>
              <label className="mb-2 block text-sm font-medium text-slate-300" htmlFor="last_name">
                Last name
              </label>
              <div className="flex items-center gap-3 rounded-2xl border border-slate-700 bg-slate-950/70 px-3 py-3">
                <UserRound size={18} className="text-slate-500" />
                <input
                  id="last_name"
                  value={formState.last_name}
                  onChange={(event) => setFormState((current) => ({ ...current, last_name: event.target.value }))}
                  className="w-full bg-transparent text-sm text-white outline-none"
                  disabled={isLoading}
                  placeholder="Last name"
                  required
                />
              </div>
            </div>
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-slate-300" htmlFor="email">
              Email address
            </label>
            <div className="flex items-center gap-3 rounded-2xl border border-slate-700 bg-slate-950/70 px-3 py-3">
              <Mail size={18} className="text-slate-500" />
              <input
                id="email"
                type="email"
                value={formState.email}
                onChange={(event) => setFormState((current) => ({ ...current, email: event.target.value }))}
                className="w-full bg-transparent text-sm text-white outline-none"
                disabled={isLoading}
                placeholder="name@example.com"
                required
              />
            </div>
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-slate-300" htmlFor="password">
              Password
            </label>
            <div className="flex items-center gap-3 rounded-2xl border border-slate-700 bg-slate-950/70 px-3 py-3">
              <ShieldCheck size={18} className="text-slate-500" />
              <input
                id="password"
                type="password"
                value={formState.password}
                  onChange={(event) => setFormState((current) => ({ ...current, password: event.target.value }))}
                className="w-full bg-transparent text-sm text-white outline-none"
                disabled={isLoading}
                placeholder="At least 8 characters"
                required
              />
            </div>
          </div>

            <div>
              <label className="mb-2 block text-sm font-medium text-slate-300" htmlFor="confirm_password">
                Confirm password
              </label>
              <div className="flex items-center gap-3 rounded-2xl border border-slate-700 bg-slate-950/70 px-3 py-3">
                <ShieldCheck size={18} className="text-slate-500" />
                <input
                  id="confirm_password"
                  type="password"
                  value={formState.confirmPassword}
                  onChange={(event) => setFormState((current) => ({ ...current, confirmPassword: event.target.value }))}
                  className="w-full bg-transparent text-sm text-white outline-none"
                  disabled={isLoading}
                  placeholder="Repeat your password"
                  required
                />
              </div>
            </div>

          {validationMessage ? (
            <div className="rounded-2xl border border-slate-700 bg-slate-950/60 px-4 py-3 text-sm text-slate-400">
              {validationMessage}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={!canSubmit || isLoading}
            className="flex w-full items-center justify-center gap-2 rounded-2xl bg-emerald-500 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-400"
          >
            {isLoading ? 'Creating account...' : 'Create account'}
            <ArrowRight size={16} />
          </button>
        </form>

        <div className="mt-6 text-center text-sm text-slate-400">
          Already have an account?{' '}
          <a className="font-medium text-emerald-300 transition hover:text-emerald-200" href="/login">
            Sign in
          </a>
        </div>
      </div>
    </div>
  );
};
