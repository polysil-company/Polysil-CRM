function wholeSeconds(totalSeconds: number): number {
  return Number.isFinite(totalSeconds) ? Math.max(0, Math.floor(totalSeconds)) : 0;
}

/** 272 → "4:32", 9 → "0:09". For countdowns shorter than an hour. */
export function formatCountdown(totalSeconds: number): string {
  const safe = wholeSeconds(totalSeconds);
  const seconds = safe % 60;
  return `${Math.floor(safe / 60)}:${String(seconds).padStart(2, "0")}`;
}

/** 272 → "4 minutes 32 seconds", 60 → "1 minute". What a screen reader should say for a countdown. */
export function describeCountdown(totalSeconds: number): string {
  const safe = wholeSeconds(totalSeconds);
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  const parts = [
    minutes > 0 ? `${minutes} ${minutes === 1 ? "minute" : "minutes"}` : "",
    seconds > 0 || minutes === 0 ? `${seconds} ${seconds === 1 ? "second" : "seconds"}` : "",
  ];
  return parts.filter((part) => part !== "").join(" ");
}
