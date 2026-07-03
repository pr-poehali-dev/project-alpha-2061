import { useState } from "react"
import { createPortal } from "react-dom"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useToast } from "@/hooks/use-toast"
import Icon from "@/components/ui/icon"

const SUBMISSIONS_URL = "https://functions.poehali.dev/7ce7a415-986b-4b02-89ac-6c6edcf527a7"

interface PdfResultViewerProps {
  submissionId: number
  pdfUrl: string
  initialTelegramContact?: string
}

export default function PdfResultViewer({ submissionId, pdfUrl, initialTelegramContact }: PdfResultViewerProps) {
  const { toast } = useToast()
  const [telegramContact, setTelegramContact] = useState(initialTelegramContact || "")
  const [isSending, setIsSending] = useState(false)
  const [isSent, setIsSent] = useState(false)
  const [showSendForm, setShowSendForm] = useState(false)

  const handleSend = async () => {
    if (!telegramContact.trim()) {
      toast({ title: "Укажите ваш Telegram или номер", variant: "destructive" })
      return
    }
    setIsSending(true)
    try {
      const response = await fetch(`${SUBMISSIONS_URL}?action=send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: submissionId, telegram_contact: telegramContact }),
      })
      if (!response.ok) throw new Error("Не удалось отправить")
      setIsSent(true)
      toast({ title: "Отправлено!", description: "Мы свяжемся с вами в Telegram" })
    } catch {
      toast({ title: "Ошибка отправки", variant: "destructive" })
    } finally {
      setIsSending(false)
    }
  }

  return createPortal(
    <div className="fixed inset-0 z-[10000] flex flex-col bg-[#0f1629]">
      <div className="flex items-center justify-between gap-4 px-5 py-4 border-b border-white/10 bg-[#0f1629]">
        <span className="text-white font-semibold">Ваше готовое КП</span>
        <div className="flex items-center gap-3">
          <a
            href={pdfUrl}
            download
            className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-4 py-2 text-sm text-white hover:bg-white/20 transition-colors"
          >
            <Icon name="Download" size={16} />
            Скачать PDF
          </a>
        </div>
      </div>

      <div className="flex-1 overflow-hidden">
        <iframe src={pdfUrl} title="Готовое КП" className="w-full h-full border-none bg-white" />
      </div>

      <div className="border-t border-white/10 bg-[#0f1629] px-5 py-4 flex justify-center">
        {isSent ? (
          <div className="flex items-center gap-3 text-center">
            <div className="w-10 h-10 rounded-full bg-green-500/20 flex items-center justify-center">
              <Icon name="Check" size={20} className="text-green-400" />
            </div>
            <p className="text-white/80 text-sm">Заявка отправлена, мы свяжемся с вами в Telegram</p>
          </div>
        ) : showSendForm ? (
          <div className="w-full max-w-sm flex items-center gap-3">
            <Input
              value={telegramContact}
              onChange={(e) => setTelegramContact(e.target.value)}
              placeholder="@username или +7 999 000-00-00"
              className="bg-white/10 border-white/20 text-white placeholder:text-white/40"
            />
            <Button
              onClick={handleSend}
              disabled={isSending}
              className="rounded-full bg-white text-black hover:bg-white/90 h-10 font-semibold shrink-0"
            >
              {isSending ? <Icon name="Loader2" size={18} className="animate-spin" /> : "Отправить"}
            </Button>
          </div>
        ) : (
          <Button
            onClick={() => setShowSendForm(true)}
            className="rounded-full bg-white text-black hover:bg-white/90 h-12 px-8 font-semibold"
          >
            <Icon name="Send" size={18} className="mr-2" />
            Отправить в Telegram
          </Button>
        )}
      </div>
    </div>,
    document.body
  )
}
