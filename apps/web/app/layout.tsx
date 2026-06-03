import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "HUGINN // MUNINN",
  description: "AI command center for thought, memory, and security operations.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
