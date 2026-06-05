// frontend/app/user/MarkdownRenderer.tsx
"use client";

import { useState, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy } from "lucide-react";
import type { Components } from "react-markdown";

function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard
      .writeText(code)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1400);
      })
      .catch(() => {});
  }, [code]);

  return (
    <div className="codeBlock">
      <div className="codeBlockHeader">
        <span>{language || "code"}</span>
        <button className="codeCopyButton" type="button" onClick={handleCopy}>
          {copied ? <Check size={13} /> : <Copy size={13} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre>
        <code>{code}</code>
      </pre>
    </div>
  );
}

const components: Components = {
  code({ className, children, ...props }) {
    const isInline = !className;
    const language = (className ?? "").replace("language-", "");
    const code = String(children).replace(/\n$/, "");
    if (isInline) {
      return (
        <code className="inlineCode" {...props}>
          {children}
        </code>
      );
    }
    return <CodeBlock language={language} code={code} />;
  },
  table({ children }) {
    return (
      <div className="tableWrapper">
        <table>{children}</table>
      </div>
    );
  },
  img({ src, alt }) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img src={src} alt={alt ?? ""} className="markdownImage" loading="lazy" />
    );
  },
  a({ href, children }) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    );
  },
  blockquote({ children }) {
    return <blockquote className="markdownQuote">{children}</blockquote>;
  },
  p({ children }) {
    return <p style={{ margin: 0 }}>{children}</p>;
  },
  h1({ children }) {
    return <h1 style={{ fontSize: "1.4em", margin: "0.2em 0" }}>{children}</h1>;
  },
  h2({ children }) {
    return <h2 style={{ fontSize: "1.2em", margin: "0.2em 0" }}>{children}</h2>;
  },
  h3({ children }) {
    return <h3 style={{ fontSize: "1.05em", margin: "0.2em 0" }}>{children}</h3>;
  },
};

export default function MarkdownRenderer({ content }: { content: string }) {
  return (
    <div className="markdownMessage">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
