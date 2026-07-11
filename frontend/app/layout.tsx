import "./globals.css";
import "./enhancements.css";
import type { Metadata } from "next";
import AppNav from "./AppNav";
import { I18nProvider } from "./i18n";

export const metadata: Metadata = {
  title: "JimsAI",
  description: "Persistent memory reasoning runtime — grounded, verified answers.",
  icons: {
    icon: "/icon.svg",
  },
};

// Applied BEFORE paint so the saved theme/language never flashes.
const bootScript = `(function(){try{
  var m=localStorage.getItem('jimsai:theme');
  if(m==='dark'||m==='light')document.documentElement.setAttribute('data-theme',m);
  var l=localStorage.getItem('jimsai:lang');
  if(l){document.documentElement.lang=l;document.documentElement.dir=(l==='ar')?'rtl':'ltr';}
}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
        <script dangerouslySetInnerHTML={{ __html: bootScript }} />
      </head>
      <body>
        <I18nProvider>
          {/*
            The global appHeader is only shown on training/other pages.
            The /user (chat) route renders its own ChatLayout which includes
            a sidebar + mobile nav bar — it does NOT use this header.
          */}
          <header className="appHeader appHeaderGlobal">
            <AppNav />
          </header>
          {children}
        </I18nProvider>
      </body>
    </html>
  );
}
