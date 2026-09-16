import { useEffect, useState, type FormEvent } from "react";
import { Eye, EyeOff, LockKeyhole, ShieldCheck } from "lucide-react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/useAuth";
import { ApiError } from "../services/api";
import { Button, Input, LogoMark, PageLoader } from "../components/ui";

export function LoginPage() {
  const { login, isAuthenticated, loading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => setError(""), [email, password]);

  if (loading) return <PageLoader />;
  if (isAuthenticated) return <Navigate to="/dashboard" replace />;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await login(email, password);
      const destination =
        (location.state as { from?: { pathname?: string } } | null)?.from
          ?.pathname ?? "/dashboard";
      navigate(destination, { replace: true });
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401)
        setError("The email or password is incorrect.");
      else if (caught instanceof ApiError && caught.status === 429)
        setError("Too many attempts. Wait a moment and try again.");
      else
        setError(
          caught instanceof Error ? caught.message : "Unable to sign in.",
        );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="relative grid min-h-screen overflow-hidden bg-void lg:grid-cols-[1.1fr_.9fr]">
      <div className="pointer-events-none absolute inset-0 bg-grid bg-[size:48px_48px] [mask-image:linear-gradient(to_bottom,black,transparent_80%)]" />
      <section className="relative hidden min-h-screen flex-col justify-between overflow-hidden border-r border-line/60 p-12 lg:flex xl:p-16">
        <div className="absolute left-[18%] top-[18%] h-80 w-80 rounded-full bg-kandor-400/[.05] blur-3xl" />
        <div className="flex items-center gap-3">
          <LogoMark className="h-11 w-11" />
          <div>
            <div className="text-lg font-bold tracking-[.24em] text-white">
              KANDOR
            </div>
            <div className="text-[9px] uppercase tracking-[.18em] text-kandor-400/70">
              Security operations fabric
            </div>
          </div>
        </div>

        <div className="relative max-w-2xl">
          <div className="mb-7 inline-flex items-center gap-2 rounded-full border border-kandor-400/20 bg-kandor-400/[.05] px-3 py-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-kandor-400 shadow-signal" />
            <span className="text-[10px] font-bold uppercase tracking-[.16em] text-kandor-200">
              Defensive telemetry, under your control
            </span>
          </div>
          <h1 className="max-w-xl text-5xl font-semibold leading-[1.05] tracking-[-.04em] text-white xl:text-6xl">
            Observe every endpoint.
            <br />
            <span className="text-slate-600">Command with restraint.</span>
          </h1>
          <p className="mt-6 max-w-lg text-base leading-7 text-slate-500">
            A self-hosted security agent orchestration platform built around
            explicit diagnostic allowlists, transparent telemetry, and immutable
            accountability.
          </p>
        </div>

        <div className="grid max-w-xl grid-cols-3 gap-3">
          {["Allowlisted tasks", "RBAC enforced", "Every action audited"].map(
            (item, index) => (
              <div key={item} className="border-l border-line pl-3">
                <span className="font-mono text-[10px] text-kandor-400">
                  0{index + 1}
                </span>
                <p className="mt-1 text-[10px] uppercase tracking-[.08em] text-slate-500">
                  {item}
                </p>
              </div>
            ),
          )}
        </div>
      </section>

      <section className="relative flex min-h-screen items-center justify-center p-6 sm:p-10">
        <div className="w-full max-w-md animate-slide-in">
          <div className="mb-9 flex items-center gap-3 lg:hidden">
            <LogoMark className="h-11 w-11" />
            <span className="text-xl font-bold tracking-[.24em]">KANDOR</span>
          </div>
          <div className="mb-8">
            <div className="mb-5 grid h-11 w-11 place-items-center rounded-xl border border-line bg-panel">
              <LockKeyhole className="h-5 w-5 text-kandor-400" />
            </div>
            <h2 className="text-3xl font-semibold tracking-tight text-white">
              Secure access
            </h2>
            <p className="mt-2 text-sm text-slate-500">
              Authenticate to enter the KANDOR command surface.
            </p>
          </div>

          <form onSubmit={submit} className="space-y-5">
            <div>
              <label className="label" htmlFor="email">
                Email address
              </label>
              <Input
                id="email"
                name="email"
                type="email"
                autoComplete="username"
                required
                autoFocus
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="operator@example.local"
              />
            </div>
            <div>
              <label className="label" htmlFor="password">
                Password
              </label>
              <div className="relative">
                <Input
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="pr-11"
                />
                <button
                  type="button"
                  className="absolute right-0 top-0 grid h-10 w-10 place-items-center text-slate-600 hover:text-slate-300"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  onClick={() => setShowPassword((shown) => !shown)}
                >
                  {showPassword ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </button>
              </div>
            </div>
            {error && (
              <div
                className="rounded-lg border border-red-500/25 bg-red-500/[.07] px-3 py-2.5 text-xs text-red-300"
                role="alert"
              >
                {error}
              </div>
            )}
            <Button className="w-full" type="submit" loading={submitting}>
              Authenticate
            </Button>
          </form>

          <div className="mt-8 flex items-center gap-2 border-t border-line/60 pt-5 text-[10px] uppercase tracking-[.1em] text-slate-700">
            <ShieldCheck className="h-3.5 w-3.5 text-slate-600" /> Encrypted
            session · rate limited · audited
          </div>
        </div>
      </section>
    </main>
  );
}
