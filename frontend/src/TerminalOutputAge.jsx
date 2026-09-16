import { useEffect, useState } from "react";

export const OUTPUT_AGE_THRESHOLD_SECONDS = 5;

export function formatOutputAge(updatedAt, now = Date.now()) {
  if (!updatedAt) return null;
  const parsed = Date.parse(updatedAt);
  if (!Number.isFinite(parsed)) return null;
  const seconds = Math.max(0, Math.floor((now - parsed) / 1000));
  if (seconds < OUTPUT_AGE_THRESHOLD_SECONDS) return null;
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600)
    return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  if (seconds < 86400)
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  return `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h`;
}

export function TerminalOutputAge({ updatedAt, title }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [updatedAt]);

  const value = formatOutputAge(updatedAt, now);
  if (!value) return null;
  return (
    <time
      className="terminal-selection-activity"
      dateTime={updatedAt}
      title={title}
      aria-label={`距最后输出 ${value}`}
    >
      {value}
    </time>
  );
}
