import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Mads",
  description: "Personal AI Chief of Staff",
  icons: {
    icon: "/mads-icon.png",
    apple: "/mads-icon.png",
  },
};

// viewport-fit=cover lets the page draw under the notch/Dynamic Island so
// env(safe-area-inset-*) below actually has a nonzero value to push content
// clear of it — without this, iOS letterboxes the page above the notch
// instead and the insets are always 0.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="h-full flex flex-col bg-bg text-text">{children}</body>
    </html>
  );
}
