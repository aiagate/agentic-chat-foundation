import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Codex Microの仕組み | Input → Agent → RGB",
  description:
    "Codex MicroがCodex / ChatGPTのタスクをどう操作するのかを図解するインタラクティブガイド。",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
