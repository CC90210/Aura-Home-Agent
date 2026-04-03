"use client";

import { useState, useCallback, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Lock, ShieldCheck, AlertTriangle } from "lucide-react";

// ---------------------------------------------------------------------------
// Inner form — needs Suspense because it reads useSearchParams()
// ---------------------------------------------------------------------------

function LoginForm() {
  const [token, setToken]   = useState("");
  const [error, setError]   = useState("");
  const [loading, setLoading] = useState(false);
  const router              = useRouter();
  const searchParams        = useSearchParams();

  const handleLogin = useCallback(
    async (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      setError("");
      setLoading(true);

      try {
        const res = await fetch("/api/auth", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token }),
        });

        if (res.ok) {
          const next = searchParams.get("next") ?? "/";
          router.replace(next);
          router.refresh();
        } else {
          setError("Invalid access code. Try again.");
          setToken("");
        }
      } catch {
        setError("Connection error. Check your network and try again.");
      } finally {
        setLoading(false);
      }
    },
    [token, router, searchParams]
  );

  return (
    <form onSubmit={handleLogin} className="flex flex-col gap-4" noValidate>
      {/* Access code input */}
      <div className="relative">
        <label htmlFor="access-code" className="sr-only">
          Access code
        </label>

        {/* Lock icon inside input */}
        <div className="absolute left-4 top-1/2 -translate-y-1/2 pointer-events-none">
          <Lock size={15} aria-hidden="true" style={{ color: error ? "#EF4444" : "#64748B" }} />
        </div>

        <input
          id="access-code"
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="Enter access code"
          autoComplete="current-password"
          autoFocus
          required
          disabled={loading}
          className={[
            "w-full pl-11 pr-4 py-4 rounded-2xl text-aura-text placeholder-aura-text-muted",
            "text-sm font-medium",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            "transition-all duration-200 outline-none",
          ].join(" ")}
          style={{
            background: "rgba(18,18,42,0.80)",
            border: error
              ? "2px solid rgba(239,68,68,0.70)"
              : token.length > 0
              ? "2px solid rgba(124,58,237,0.70)"
              : "2px solid rgba(30,30,64,0.80)",
            boxShadow: error
              ? "0 0 0 4px rgba(239,68,68,0.10)"
              : token.length > 0
              ? "0 0 0 4px rgba(124,58,237,0.12), inset 0 1px 0 rgba(255,255,255,0.05)"
              : "inset 0 1px 0 rgba(255,255,255,0.04)",
          }}
        />
      </div>

      {/* Error message */}
      {error && (
        <div
          className="flex items-center gap-2 rounded-xl px-3 py-2.5"
          style={{
            background: "rgba(239,68,68,0.10)",
            border: "1px solid rgba(239,68,68,0.25)",
            animation: "fade-in 0.25s ease-out",
          }}
          role="alert"
        >
          <AlertTriangle size={14} className="text-aura-red shrink-0" aria-hidden="true" />
          <p className="text-aura-red text-xs font-medium">{error}</p>
        </div>
      )}

      {/* Submit */}
      <button
        type="submit"
        disabled={loading || token.length === 0}
        className={[
          "w-full py-4 rounded-2xl font-bold text-sm text-white",
          "transition-all duration-200",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aura-purple/60 focus-visible:ring-offset-2",
          "focus-visible:ring-offset-aura-darker",
          "active:scale-[0.98]",
          loading || token.length === 0
            ? "cursor-not-allowed opacity-50"
            : "cursor-pointer hover:brightness-110",
        ].join(" ")}
        style={
          loading || token.length === 0
            ? { background: "rgba(124,58,237,0.30)" }
            : {
                background: "linear-gradient(135deg, #7C3AED 0%, #5B21B6 50%, #3B82F6 100%)",
                boxShadow: "0 0 24px rgba(124,58,237,0.45), 0 4px 12px rgba(0,0,0,0.30)",
              }
        }
      >
        {loading ? (
          <span className="flex items-center justify-center gap-2">
            <span
              className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white"
              style={{ animation: "spin 0.8s linear infinite" }}
              aria-hidden="true"
            />
            <span>Verifying&hellip;</span>
          </span>
        ) : (
          <span className="flex items-center justify-center gap-2">
            <ShieldCheck size={16} aria-hidden="true" />
            Enter AURA
          </span>
        )}
      </button>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function LoginPage() {
  return (
    <div
      className="min-h-dvh flex items-center justify-center px-4"
      style={{ background: "#06060F" }}
    >
      {/* Ambient background glows */}
      <div aria-hidden="true" className="pointer-events-none fixed inset-0 overflow-hidden">
        {/* Large top-center purple bloom */}
        <div
          className="absolute left-1/2 -translate-x-1/2 rounded-full"
          style={{
            top: "-15%",
            width: "80vw",
            height: "70vh",
            background: "radial-gradient(ellipse, rgba(124,58,237,0.18) 0%, transparent 70%)",
            filter: "blur(40px)",
          }}
        />
        {/* Bottom blue accent */}
        <div
          className="absolute left-1/2 -translate-x-1/2 rounded-full"
          style={{
            bottom: "-10%",
            width: "60vw",
            height: "40vh",
            background: "radial-gradient(ellipse, rgba(59,130,246,0.10) 0%, transparent 70%)",
            filter: "blur(40px)",
          }}
        />
        {/* Subtle grid lines overlay */}
        <div
          className="absolute inset-0"
          style={{
            backgroundImage:
              "linear-gradient(rgba(124,58,237,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(124,58,237,0.03) 1px, transparent 1px)",
            backgroundSize: "40px 40px",
          }}
        />
      </div>

      {/* Card */}
      <div
        className="relative z-10 w-full max-w-sm"
        style={{ animation: "slide-up 0.5s ease-out both" }}
      >
        <div
          className="rounded-3xl p-8"
          style={{
            background: "rgba(12,12,28,0.90)",
            backdropFilter: "blur(24px)",
            WebkitBackdropFilter: "blur(24px)",
            border: "1px solid rgba(124,58,237,0.18)",
            boxShadow:
              "0 0 0 1px rgba(255,255,255,0.04) inset, 0 8px 64px rgba(0,0,0,0.60), 0 0 80px rgba(124,58,237,0.08)",
          }}
        >
          {/* Icon + wordmark */}
          <div className="flex flex-col items-center mb-8">
            {/* Glowing lock icon */}
            <div
              className="w-16 h-16 rounded-2xl flex items-center justify-center mb-6 login-icon-glow"
              style={{
                background: "rgba(124,58,237,0.15)",
                border: "1px solid rgba(124,58,237,0.35)",
              }}
            >
              <Lock size={28} className="text-aura-purple-light" aria-hidden="true" />
            </div>

            {/* AURA wordmark */}
            <h1
              className="text-4xl font-black tracking-[0.22em] wordmark-glow"
              style={{
                backgroundImage: "linear-gradient(135deg, #9F67FF 0%, #60A5FA 50%, #9F67FF 100%)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                backgroundClip: "text",
              }}
            >
              AURA
            </h1>

            {/* Subtitle */}
            <p className="text-aura-text-muted text-xs mt-2 tracking-widest uppercase">
              by OASIS &mdash; Secure Access
            </p>

            {/* Decorative rule */}
            <div
              className="mt-5 h-px w-24 rounded-full"
              aria-hidden="true"
              style={{ background: "linear-gradient(90deg, transparent, rgba(124,58,237,0.50), transparent)" }}
            />
          </div>

          {/* Login form */}
          <Suspense
            fallback={
              <div className="h-[136px] flex items-center justify-center">
                <span className="text-aura-text-muted text-sm">Loading&hellip;</span>
              </div>
            }
          >
            <LoginForm />
          </Suspense>
        </div>

        {/* Footer */}
        <p className="text-center text-xs mt-5" style={{ color: "rgba(100,116,139,0.40)" }}>
          AURA by OASIS AI Solutions &middot; v0.1.0
        </p>
      </div>
    </div>
  );
}
