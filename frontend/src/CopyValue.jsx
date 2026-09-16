import { useEffect, useRef, useState } from "react";
import { Hint } from "./Tooltip";

export async function writeClipboard(text) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch {
      /* compatible fallback */
    }
  }
  const input = document.createElement("textarea");
  input.value = text;
  input.setAttribute("readonly", "");
  input.style.cssText = "position:fixed;left:-9999px;top:0;opacity:0";
  document.body.appendChild(input);
  input.select();
  const copied = document.execCommand("copy");
  input.remove();
  if (!copied) throw new Error("copy unavailable");
}

export function CopyValue({ label, value, customText = false, ariaContext = "" }) {
  const [copied, setCopied] = useState(false);
  const timer = useRef();
  useEffect(() => () => clearTimeout(timer.current), []);
  const text =
    typeof value === "object" ? JSON.stringify(value) : String(value ?? "—");
  const copy = async () => {
    await writeClipboard(text);
    setCopied(true);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), 1200);
  };
  return (
    <div className="copy-field" data-custom-text={customText || undefined}>
      {label && <span className="copy-label">{label}</span>}
      <span className="copy-shell" data-copied={copied}>
        <Hint label={copied ? "已复制" : "点击复制"}>
          <button
            className="copy-value"
            type="button"
            onClick={copy}
            aria-label={`${label ? `${label}，` : ariaContext ? `${ariaContext}，` : customText ? `${text}，` : ""}${copied ? "已复制" : "点击复制"}`}
          >
            <code>{text}</code>
          </button>
        </Hint>
        <span className="copy-status" role="status">
          {copied ? "已复制" : ""}
        </span>
      </span>
    </div>
  );
}

export function TaskListValue({ label, values }) {
  return (
    <div className="task-list-field">
      <span className="copy-label">{label}</span>
      <div className="task-code-list" role="list" aria-label={label}>
        {values.map((value, index) => (
          <div role="listitem" key={`${label}-${index}`}>
            <CopyValue value={value} ariaContext={`${label} ${index + 1}`} />
          </div>
        ))}
      </div>
    </div>
  );
}
