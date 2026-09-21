import { Geist, Geist_Mono } from "next/font/google";

/**
 * Typeface: Geist (UI) + Geist Mono (IDs, references, codes).
 * Self-hosted by next/font at build time — no runtime requests to Google.
 * `latin-ext` carries the ₹ (U+20B9) glyph range.
 * Changing the typeface: edit this file and --font-sans/--font-mono in tokens.css.
 */
const sans = Geist({
  subsets: ["latin", "latin-ext"],
  variable: "--font-geist-sans",
  display: "swap",
});

const mono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-geist-mono",
  display: "swap",
});

export const fontVariables = `${sans.variable} ${mono.variable}`;
