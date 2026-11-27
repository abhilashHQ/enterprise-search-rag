import { PixelLogo } from "@/components/ob/logo"

export default function ChatPage() {
  return (
    <div className="mx-auto flex max-w-[760px] flex-col items-center px-6 pt-32 text-center">
      <PixelLogo size={48} />
      <h1 className="mt-6">ask me anything about redwood</h1>
    </div>
  )
}
