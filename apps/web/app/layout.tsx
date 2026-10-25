import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "Arletion — Lead Intelligence", description: "Find • Qualify • Unlock • Grow.", icons: { icon: "/arletion-icon.png", apple: "/arletion-icon.png" } };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
 return <html lang="en"><body>{children}</body></html>;
}
