import type { Metadata } from "next";
import { Nav } from "@/components/Nav";
import { WorkspaceProvider } from "@/components/Workspace";
import "./globals.css";

export const metadata: Metadata = {
  title: "BrandPilot",
  description: "Check content against your brand rules and approved facts before it goes live.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400&display=swap"
        />
      </head>
      <body className="min-h-screen">
        <WorkspaceProvider>
          <Nav />
          <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">{children}</main>
        </WorkspaceProvider>
      </body>
    </html>
  );
}
