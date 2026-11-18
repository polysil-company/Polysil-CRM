import type { DownloadedFile } from "./client";

/** How long the object URL lives after the click: long enough for every browser to start saving. */
const REVOKE_AFTER_MS = 30_000;

/**
 * Saves a downloaded file the way a browser saves a link with `download`: the backend's name
 * when it gave one, otherwise `fallbackName`. Works on phones too (the file goes to Downloads).
 */
export function saveFile(file: DownloadedFile, fallbackName: string): void {
  const url = URL.createObjectURL(file.blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = file.filename ?? fallbackName;
  link.rel = "noopener";
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => {
    URL.revokeObjectURL(url);
  }, REVOKE_AFTER_MS);
}
