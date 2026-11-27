import type { Metadata } from "next"
import { GeistMono } from "geist/font/mono"
import { GeistSans } from "geist/font/sans"

import { TooltipProvider } from "@web/components/ui/tooltip"
import "./globals.css"

export const metadata: Metadata = {
  title: "orgbrain: your company's brain, open source",
  description:
    "orgbrain reads your team's chat, email, tickets and docs, answers with sources, and remembers what the team approves. it runs on your machine.",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable} antialiased`}>
      <body className="ob min-h-dvh">
        <TooltipProvider>{children}</TooltipProvider>
      </body>
    </html>
  )
}
