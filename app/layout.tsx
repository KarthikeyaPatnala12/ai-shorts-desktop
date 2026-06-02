import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Shorts Desktop",
  description: "Local desktop app for turning long videos into short clips."
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
