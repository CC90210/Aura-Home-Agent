"use client";

import { useState, useCallback, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Lock, ShieldCheck, AlertTriangle } from "lucide-react";

// ---------------------------------------------------------------------------
// Inner form — needs Suspense because it reads useSearchParams()
// ---------------------------------------------------------------------------

function LoginForm() {
  const [token, setToken]     = useState("");
  const [error, setError]     = useState("");
  const [loading, setLoading] = useState(false);
  const router                = useRouter();
  const searchParams          = useSearchParams();

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

  const inputBorder = error
    ? "2px solid rgba(239,68,68,0.70)"
    : token.length > 0
    ? "2px solid rgba(124,58,237,0.70)"
    : "2px solid rgba(30,30,64,0.80)";

  const inputShadow = error
    ? "0 0 0 4px rgba(239,68,68,0.10)"
    : token.length > 0
    ? "0 0 0 4px rgba(124,58,237,0.12), inset 0 1px 0 rgba(255,255,255,0.05)"
    : "inset 0 1px 0 rgba(255,255,255,0.04)";

  return (
    <form onSubmit={handleLogin} style={{ display: "flex", flexDirection: "column", gap: 16 }} noValidate>
      {/* Input */}
      <div style={{ position: "relative" }}>
        <label htmlFor="access-code" style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0,0,0,0)" }}>
          Access code
        </label>
        <div
          style={{
            position: "absolute", left: 16, top: "50%",
            transform: "translateY(-50%)", pointerEvents: "none",
          }}
        >
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
          style={{
            width: "100%",
            paddingLeft: 44,
            paddingRight: 16,
            paddingTop: 16,
            paddingBottom: 16,
            borderRadius: 16,
            background: "rgba(18,18,42,0.80)",
            border: inputBorder,
            boxShadow: inputShadow,
            color: "#E2E8F0",
            fontSize: 14,
            fontWeight: 500,
            fontFamily: "inherit",
            outline: "none",
            transition: "all 0.2s",
            opacity: loading ? 0.5 : 1,
            cursor: loading ? "not-allowed" : "text",
          }}
        />
      </div>

      {/* Error message */}
      {error && (
        <div
          role="alert"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            borderRadius: 12,
            padding: "10px 12px",
            background: "rgba(239,68,68,0.10)",
            border: "1px solid rgba(239,68,68,0.25)",
            animation: "fade-in 0.25s ease-out",
          }}
        >
          <AlertTriangle size={14} style={{ color: "#EF4444", flexShrink: 0 }} aria-hidden="true" />
          <p style={{ margin: 0, color: "#EF4444", fontSize: 12, fontWeight: 500 }}>{error}</p>
        </div>
      )}

      {/* Submit button */}
      <button
        type="submit"
        disabled={loading || token.length === 0}
        style={{
          width: "100%",
          padding: "16px",
          borderRadius: 16,
          border: "none",
          fontWeight: 700,
          fontSize: 14,
          color: "white",
          fontFamily: "inherit",
          cursor: loading || token.length === 0 ? "not-allowed" : "pointer",
          transition: "all 0.2s",
          opacity: loading || token.length === 0 ? 0.5 : 1,
          background:
            loading || token.length === 0
              ? "rgba(124,58,237,0.30)"
              : "linear-gradient(135deg, #7C3AED 0%, #5B21B6 50%, #3B82F6 100%)",
          boxShadow:
            loading || token.length === 0
              ? "none"
              : "0 0 24px rgba(124,58,237,0.45), 0 4px 12px rgba(0,0,0,0.30)",
        }}
      >
        {loading ? (
          <span style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
            <span
              style={{
                width: 16, height: 16, borderRadius: "50%",
                border: "2px solid rgba(255,255,255,0.25)",
                borderTopColor: "white",
                animation: "spin 0.8s linear infinite",
                display: "inline-block",
                flexShrink: 0,
              }}
              aria-hidden="true"
            />
            Verifying&hellip;
          </span>
        ) : (
          <span style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
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
      style={{
        minHeight: "100dvh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "16px",
        background: "#06060F",
      }}
    >
      {/* Ambient background glows */}
      <div
        aria-hidden="true"
        style={{
          pointerEvents: "none",
          position: "fixed",
          inset: 0,
          overflow: "hidden",
        }}
      >
        {/* Top purple bloom */}
        <div
          style={{
            position: "absolute",
            left: "50%",
            top: "-15%",
            transform: "translateX(-50%)",
            width: "80vw",
            height: "70vh",
            borderRadius: "50%",
            background: "radial-gradient(ellipse, rgba(124,58,237,0.18) 0%, transparent 70%)",
            filter: "blur(40px)",
          }}
        />
        {/* Bottom blue accent */}
        <div
          style={{
            position: "absolute",
            left: "50%",
            bottom: "-10%",
            transform: "translateX(-50%)",
            width: "60vw",
            height: "40vh",
            borderRadius: "50%",
            background: "radial-gradient(ellipse, rgba(59,130,246,0.10) 0%, transparent 70%)",
            filter: "blur(40px)",
          }}
        />
        {/* Subtle grid overlay */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            backgroundImage:
              "linear-gradient(rgba(124,58,237,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(124,58,237,0.03) 1px, transparent 1px)",
            backgroundSize: "40px 40px",
          }}
        />
      </div>

      {/* Card */}
      <div
        style={{
          position: "relative",
          zIndex: 10,
          width: "100%",
          maxWidth: 380,
          animation: "slide-up 0.5s ease-out both",
        }}
      >
        <div
          style={{
            borderRadius: 24,
            padding: 32,
            background: "rgba(12,12,28,0.90)",
            backdropFilter: "blur(24px)",
            WebkitBackdropFilter: "blur(24px)",
            border: "1px solid rgba(124,58,237,0.18)",
            boxShadow:
              "0 0 0 1px rgba(255,255,255,0.04) inset, 0 8px 64px rgba(0,0,0,0.60), 0 0 80px rgba(124,58,237,0.08)",
          }}
        >
          {/* Icon + wordmark */}
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", marginBottom: 32 }}>
            {/* Glowing icon */}
            <div
              className="login-icon-glow"
              style={{
                width: 64,
                height: 64,
                borderRadius: 18,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background: "rgba(124,58,237,0.15)",
                border: "1px solid rgba(124,58,237,0.35)",
                marginBottom: 24,
              }}
            >
              <Lock size={28} style={{ color: "#A78BFA" }} aria-hidden="true" />
            </div>

            {/* AURA wordmark */}
            <h1
              className="wordmark-glow"
              style={{
                margin: 0,
                fontSize: 36,
                fontWeight: 900,
                letterSpacing: "0.22em",
                backgroundImage: "linear-gradient(135deg, #9F67FF 0%, #60A5FA 50%, #9F67FF 100%)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                backgroundClip: "text",
              }}
            >
              AURA
            </h1>

            {/* Subtitle */}
            <p
              style={{
                margin: "8px 0 0",
                color: "#64748B",
                fontSize: 11,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
              }}
            >
              by OASIS &mdash; Secure Access
            </p>

            {/* Decorative rule */}
            <div
              aria-hidden="true"
              style={{
                marginTop: 20,
                height: 1,
                width: 96,
                borderRadius: 2,
                background: "linear-gradient(90deg, transparent, rgba(124,58,237,0.50), transparent)",
              }}
            />
          </div>

          {/* Login form */}
          <Suspense
            fallback={
              <div style={{ height: 136, display: "flex", alignItems: "center", justifyContent: "center" }}>
                <span style={{ color: "#64748B", fontSize: 13 }}>Loading&hellip;</span>
              </div>
            }
          >
            <LoginForm />
          </Suspense>
        </div>

        {/* Footer */}
        <p
          style={{
            textAlign: "center",
            fontSize: 11,
            marginTop: 20,
            color: "rgba(100,116,139,0.40)",
          }}
        >
          AURA by OASIS AI Solutions &middot; v0.1.0
        </p>
      </div>
    </div>
  );
}
