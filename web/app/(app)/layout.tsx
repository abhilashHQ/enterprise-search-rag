import type { Metadata } from "next"

import { LightOnly, Shell } from "@/components/ob/shell"
import "./orgbrain.css"

export const metadata: Metadata = {
  title: "orgbrain",
  description: "your company's brain, cited",
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="ob flex min-h-dvh">
      <LightOnly />
      <Shell>{children}</Shell>
    </div>
  )
}
