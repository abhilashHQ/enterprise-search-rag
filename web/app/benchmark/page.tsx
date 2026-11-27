import type { Metadata } from "next"

import { DemoApp } from "@/components/demo-app"

export const metadata: Metadata = {
  title: "Enterprise Search - cited answers over company documents",
  description: "Hybrid retrieval, reranking, cited answers and a confidence check over 512K company documents.",
}

export default function Benchmark() {
  return <DemoApp />
}
