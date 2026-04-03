"use client";

import { useState, useCallback, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Lock } from "lucide-react";

// ---------------------------------------------------------------------------
// Inner form — needs Suspense because it reads useSearchParams()
// ---------------------------------------------------------------------------

function LoginForm() {
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const searchParams = useSearchParams();

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
    <form onSubmit={handleLogin} className="space-y-4" noValidate>
      {/* Input */}
      <div className="relative">
        <label htmlFor="access-code" className="sr-only">
          Access code
        </label>
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
            "w-full px-4 py-3.5 rounded-2xl text-aura-text placeholder-aura-text-muted",
            "bg-aura-card border text-sm",
            "focus:outline-none focus-visible:ring-2",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            "transition-all duration-200",
            error
              ? "border-aura-red/60 focus-visible:ring-aura-red/50"
              : "border-aura-border focus:border-aura-purple focus-visible:ring-aura-purple/40",
          ]
            .filter(Boolean)
            .join(" ")}
        />
      </div>

      {/* Error message */}
      {error && (
        <p
          role="alert"
          className="text-aura-red text-sm text-center animate-[fade-in_0.25s_ease-out]"
        >
          {error}
        </p>
      )}

      {/* Submit button */}
      <button
        type="submit"
        disabled={loading || token.length === 0}
        className={[
          "w-full py-3.5 rounded-2xl font-semibold text-sm text-white",
          "transition-all duration-200",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aura-purple/60",
          "active:scale-[0.98]",
          loading || token.length === 0
            ? "bg-aura-purple/40 cursor-not-allowed opacity-60"
            : "bg-aura-purple hover:bg-aura-purple-light cursor-pointer shadow-[0_0_20px_rgba(124,58,237,0.35)]",
        ].join(" ")}
      >
        {loading ? (
          <span className="flex items-center justify-center gap-2">
            <span className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-[spin_0.8s_linear_infinite]" />
            Verifying...
          </span>
        ) : (
          "Enter"
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
    <div className="min-h-screen bg-aura-dark flex items-center justify-center px-4">
      {/* Ambient glow behind the card */}
      <div
        aria-hidden="true"
        className="pointer-events-none fixed inset-0 overflow-hidden"
      >
        <div
          className="absolute -top-32 left-1/2 -translate-x-1/2 h-[500px] w-[700px] rounded-full blur-[130px]"
          style={{ background: "rgba(124,58,237,0.10)" }}
        />
        <div
          className="absolute bottom-0 left-1/2 -translate-x-1/2 h-[300px] w-[500px] rounded-full blur-[100px]"
          style={{ background: "rgba(59,130,246,0.06)" }}
        />
      </div>

      <div className="relative z-10 w-full max-w-sm animate-[slide-up_0.4s_ease-out]">
        {/* Card */}
        <div className="glass-card rounded-3xl p-8">
          {/* Lock icon + wordmark */}
          <div className="text-center mb-8">
            <div className="flex items-center justify-center mb-5">
              <div
                className="w-16 h-16 rounded-2xl flex items-center justify-center"
                style={{
                  background: "rgba(124,58,237,0.15)",
                  border: "1px solid rgba(124,58,237,0.30)",
                  boxShadow: "0 0 24px rgba(124,58,237,0.20)",
                }}
              >
                <Lock size={28} className="text-aura-purple-light" aria-hidden="true" />
              </div>
            </div>

            <h1
              className="text-4xl font-black tracking-[0.22em] text-transparent bg-clip-text"
              style={{
                backgroundImage:
                  "linear-gradient(135deg, #9F67FF 0%, #60A5FA 50%, #9F67FF 100%)",
              }}
            >
              AURA
            </h1>
            <p className="text-aura-text-muted mt-2 text-sm tracking-wide">
              by OASIS &mdash; Enter your access code
            </p>
          </div>

          {/* Login form — needs Suspense for useSearchParams */}
          <Suspense
            fallback={
              <div className="h-[116px] flex items-center justify-center">
                <span className="text-aura-text-muted text-sm">Loading...</span>
              </div>
            }
          >
            <LoginForm />
          </Suspense>
        </div>

        {/* Footer */}
        <p className="text-aura-text-muted/40 text-xs text-center mt-6 tracking-wide">
          AURA by OASIS AI Solutions
        </p>
      </div>
    </div>
  );
}
