import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "AI Video Editor",
  description: "Private AI video editing automation dashboard"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

