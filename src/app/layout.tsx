import "./globals.css";
import type { Metadata } from "next";
import { Sidebar } from "@/lib/ui/Sidebar";

export const metadata: Metadata = {
  title: "Maxey0 Latent Space Lab",
  description: "Constitution-axis latent mapping, snapshots, Voronoi/Delaunay dual graphs, and dataset generation.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen flex">
          <Sidebar />
          <main className="flex-1 p-6">{children}</main>
        </div>
      </body>
    </html>
  );
}
