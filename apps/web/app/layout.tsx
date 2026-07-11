import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "HUGINN // MUNINN",
  description: "Defensive intelligence dashboard connecting security telemetry, MITRE ATT&CK context, and evidence-backed analysis.",
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
