import { Chat } from "@/components/ob/chat"

export default async function ChatPage({ searchParams }: PageProps<"/">) {
  const { q } = await searchParams
  return <Chat initialInput={typeof q === "string" ? q : ""} />
}
