import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ODD/EVEN AI TRADER | Algorithmic Quantitative Platform",
  description: "Plataforma quantitativa de alta frequência para contratos de dígitos Even/Odd na Deriv",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pt-BR" className="dark">
      <body className="min-h-screen bg-dark-900 text-gray-100 antialiased selection:bg-cyan-500 selection:text-black">
        {children}
      </body>
    </html>
  );
}
