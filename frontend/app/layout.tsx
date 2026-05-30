import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";
import AppNav from "./AppNav";

export const metadata: Metadata = {
  title: "JIMS-AI",
  description: "Deterministic semantic execution runtime",
  icons: {
    icon: "/icon.svg"
  }
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="appHeader">
          <Link className="brandLink" href="/user">
            <span className="brandMark">J</span>
            <span>
              <strong>JIMS-AI</strong>
              <small>Persistent chat runtime</small>
            </span>
          </Link>
          <AppNav />
        </header>
        {children}
      </body>
    </html>
  );
}
