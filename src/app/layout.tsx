import Header from "@/components/Header";
import Footer from "@/components/Footer";
import type { Metadata } from "next";
import { Inter, Playfair_Display, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const playfair = Playfair_Display({
  variable: "--font-playfair",
  subsets: ["latin"],
  style: ["normal", "italic"],
  weight: ["400", "500", "600", "700", "900"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: {
    default: "Veritas — The truth behind the story",
    template: "%s · Veritas",
  },
  description:
    "Veritas examines text, images, audio and video at six desks, and signs a record of what it found.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      {/* `bg-background` is the ground for the whole site. It was missing entirely:
          html and body carried no background-colour at all, so the only thing
          painting the page was the fixed photograph behind it, and any frame in
          which that layer had not painted rendered the page on a transparent
          canvas. The photograph now belongs to the front page (src/app/page.tsx). */}
      <body
        className={`${inter.variable} ${playfair.variable} ${jetbrainsMono.variable} bg-background text-ink-black font-body-lg min-h-screen relative overflow-x-hidden selection:bg-gold-foil selection:text-ink-black`}
      >
        <Header />
        {children}
        <Footer />
      </body>
    </html>
  );
}
