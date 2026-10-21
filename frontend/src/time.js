export const showTime = (value) => value
  ? new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
    second: '2-digit', hourCycle: 'h23',
  }).format(new Date(value))
  : '—';

export function localInputValue(value) {
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000)
    .toISOString().slice(0, 19).replace('T', ' ');
}

export function parseLocalTime(value) {
  if (!/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value)) return null;
  const date = new Date(value.replace(' ', 'T'));
  // Reject normalization of impossible dates and local daylight-saving gaps.
  return Number.isFinite(date.getTime()) && localInputValue(date) === value ? date : null;
}
