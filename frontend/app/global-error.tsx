"use client";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en">
      <body>
        <main className="authShell">
          <section className="authCard">
            <div>
              <p className="eyebrow">Application Error</p>
              <h1>JIMS-AI could not render</h1>
              <p>{error.message || "The frontend hit an unexpected error."}</p>
            </div>
            <button className="sendButton" type="button" onClick={reset}>
              Try again
            </button>
          </section>
        </main>
      </body>
    </html>
  );
}
