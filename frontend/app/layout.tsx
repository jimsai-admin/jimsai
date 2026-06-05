import "./globals.css";
import type { Metadata } from "next";
import AppNav from "./AppNav";

export const metadata: Metadata = {
  title: "JimsAI",
  description: "Persistent memory reasoning runtime",
  icons: {
    icon: "/icon.svg",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {/*
          The global appHeader is only shown on training/other pages.
          The /user (chat) route renders its own ChatLayout which includes
          a sidebar + mobile nav bar — it does NOT use this header.
          We keep the header in the DOM but hide it for the chat route
          via CSS when .chatRoot is present in the page body.
        */}
        <header className="appHeader appHeaderGlobal">
          <AppNav />
        </header>
        {children}
      </body>
    </html>
  );
}
