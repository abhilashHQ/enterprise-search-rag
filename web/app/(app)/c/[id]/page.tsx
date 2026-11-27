import { Chat } from "@/components/ob/chat"

export default async function ConversationPage({ params }: PageProps<"/c/[id]">) {
  const { id } = await params
  return <Chat key={id} conversationId={id} />
}
