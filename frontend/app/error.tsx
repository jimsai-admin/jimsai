"use client";

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="authShell">
      <section className="authCard">
        <div>
          <p className="eyebrow">Runtime Error</p>
          <h1>Something went wrong</h1>
          <p>{error.message || "The interface hit an unexpected error."}</p>
        </div>
        <button className="sendButton" type="button" onClick={reset}>
          Try again
        </button>
      </section>
    </main>
  );
}
