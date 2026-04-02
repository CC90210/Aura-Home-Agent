"use client";

import { useState, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

// ---------------------------------------------------------------------------
// Inner form component — reads search params (requires Suspense boundary)
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
          // Redirect to the originally requested URL, or the dashboard root.
          const next = searchParams.get("next") ?? "/";
          // router.replace avoids adding the login page to browser history.
          router.replace(next);
          router.refresh();
        } else {
          setError("Invalid access code. Try again.");
          // Clear the field so the user cannot resubmit the same bad token.
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
      <div>
        <label htmlFor="access-code" className="sr-only">
          Access code
        </label>
        <input
          id="access-code"
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="Access code"
          autoComplete="current-password"
          autoFocus
          required
          disabled={loading}
          className={[
            "w-full px-4 py-3 rounded-xl",
            "bg-[#1A1A2E] border text-white placeholder-gray-500",
            "focus:outline-none focus:ring-1",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            "transition-colors",
            error
              ? "border-red-500/60 focus:border-red-500 focus:ring-red-500"
              : "border-gray-700 focus:border-purple-500 focus:ring-purple-500",
          ]
            .filter(Boolean)
            .join(" ")}
        />
      </div>

      {error && (
        <p role="alert" className="text-red-400 text-sm text-center">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={loading || token.length === 0}
        className={[
          "w-full py-3 rounded-xl font-medium transition-colors",
          "bg-purple-600 hover:bg-purple-500 text-white",
          "disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-purple-600",
        ].join(" ")}
      >
        {loading ? "Verifying..." : "Enter"}
      </button>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function LoginPage() {
  return (
    <div className="min-h-screen bg-[#0F0F1A] flex items-center justify-center px-4">
      {/*
        Ambient background glow — matches the main dashboard aesthetic so
        the login page feels like part of the same product.
      */}
      <div
        aria-hidden="true"
        className="pointer-events-none fixed inset-0 overflow-hidden"
      >
        <div className="absolute -top-40 left-1/2 -translate-x-1/2 h-[600px] w-[800px] rounded-full bg-purple-600 opacity-[0.06] blur-[120px]" />
      </div>

      <div className="relative z-10 w-full max-w-sm">
        {/* Wordmark */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-black tracking-[0.2em] text-transparent bg-clip-text bg-gradient-to-r from-purple-400 via-blue-400 to-purple-400">
            AURA
          </h1>
          <p className="text-gray-400 mt-2 text-sm">
            by OASIS &mdash; Enter your access code
          </p>
        </div>

        {/*
          Suspense is required because LoginForm uses useSearchParams(), which
          relies on the dynamic request context at render time.
        */}
        <Suspense
          fallback={
            <div className="h-[120px] flex items-center justify-center">
              <span className="text-gray-500 text-sm">Loading...</span>
            </div>
          }
        >
          <LoginForm />
        </Suspense>

        <p className="text-gray-600 text-xs text-center mt-8">
          AURA by OASIS AI Solutions
        </p>
      </div>
    </div>
  );
}
