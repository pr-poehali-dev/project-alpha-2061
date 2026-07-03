import { useState } from "react"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"
import { useToast } from "@/hooks/use-toast"
import Icon from "@/components/ui/icon"
import KpEditor, { GeneratedContent } from "@/components/KpEditor"

const SUBMISSIONS_URL = "https://functions.poehali.dev/7ce7a415-986b-4b02-89ac-6c6edcf527a7"

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result as string
      resolve(result.split(",")[1])
    }
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

export default function UploadForm() {
  const { toast } = useToast()
  const [name, setName] = useState("")
  const [telegramContact, setTelegramContact] = useState("")
  const [oldKp, setOldKp] = useState<File | null>(null)
  const [referenceKp, setReferenceKp] = useState<File | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [result, setResult] = useState<{ id: number; generated_content: GeneratedContent } | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!name || !telegramContact || !oldKp || !referenceKp) {
      toast({
        title: "Заполните все поля",
        description: "Укажите имя, телеграм и загрузите оба файла",
        variant: "destructive",
      })
      return
    }

    setIsSubmitting(true)

    try {
      const [oldKpData, referenceKpData] = await Promise.all([
        fileToBase64(oldKp),
        fileToBase64(referenceKp),
      ])

      const response = await fetch(`${SUBMISSIONS_URL}?action=generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          telegram_contact: telegramContact,
          old_kp_file: {
            filename: oldKp.name,
            content_type: oldKp.type || "application/octet-stream",
            data: oldKpData,
          },
          reference_kp_file: {
            filename: referenceKp.name,
            content_type: referenceKp.type || "application/octet-stream",
            data: referenceKpData,
          },
        }),
      })

      if (!response.ok) {
        const err = await response.json().catch(() => ({}))
        throw new Error(err.error || "Не удалось отправить заявку")
      }

      const data = await response.json()
      setResult({ id: data.id, generated_content: data.generated_content })
      toast({
        title: "Готово!",
        description: "Ваше новое КП сгенерировано",
      })
    } catch (err) {
      toast({
        title: "Ошибка отправки",
        description: err instanceof Error ? err.message : "Попробуйте ещё раз",
        variant: "destructive",
      })
    } finally {
      setIsSubmitting(false)
    }
  }

  if (result) {
    return (
      <KpEditor
        submissionId={result.id}
        initialContent={result.generated_content}
        initialTelegramContact={telegramContact}
      />
    )
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="w-full max-w-xl rounded-3xl border border-white/20 bg-white/10 p-8 backdrop-blur-md flex flex-col gap-5"
    >
      <div className="flex flex-col gap-1 text-center mb-2">
        <h3 className="text-2xl font-semibold text-white">Загрузите файлы</h3>
        <p className="text-white/70 text-sm">
          Ваше текущее КП и пример дизайна, который вам нравится
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="flex flex-col gap-2">
          <Label htmlFor="name" className="text-white/90">Имя</Label>
          <Input
            id="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Ваше имя"
            className="bg-white/10 border-white/20 text-white placeholder:text-white/40"
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="telegram" className="text-white/90">Telegram или номер</Label>
          <Input
            id="telegram"
            value={telegramContact}
            onChange={(e) => setTelegramContact(e.target.value)}
            placeholder="@username или +7 999 000-00-00"
            className="bg-white/10 border-white/20 text-white placeholder:text-white/40"
          />
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <Label className="text-white/90">Ваше текущее КП</Label>
        <label
          htmlFor="old_kp"
          className="flex items-center gap-3 rounded-xl border border-dashed border-white/30 bg-white/5 px-4 py-3 cursor-pointer hover:bg-white/10 transition-colors"
        >
          <Icon name="FileText" size={20} className="text-white/70 shrink-0" />
          <span className="text-white/80 text-sm truncate">
            {oldKp ? oldKp.name : "Выберите PDF или файл КП"}
          </span>
        </label>
        <input
          id="old_kp"
          type="file"
          accept=".pdf,.doc,.docx"
          className="hidden"
          onChange={(e) => setOldKp(e.target.files?.[0] || null)}
        />
      </div>

      <div className="flex flex-col gap-2">
        <Label className="text-white/90">Пример дизайна, который нравится</Label>
        <label
          htmlFor="reference_kp"
          className="flex items-center gap-3 rounded-xl border border-dashed border-white/30 bg-white/5 px-4 py-3 cursor-pointer hover:bg-white/10 transition-colors"
        >
          <Icon name="Sparkles" size={20} className="text-white/70 shrink-0" />
          <span className="text-white/80 text-sm truncate">
            {referenceKp ? referenceKp.name : "Выберите PDF-пример дизайна"}
          </span>
        </label>
        <input
          id="reference_kp"
          type="file"
          accept=".pdf,.doc,.docx"
          className="hidden"
          onChange={(e) => setReferenceKp(e.target.files?.[0] || null)}
        />
      </div>

      <Button
        type="submit"
        disabled={isSubmitting}
        className="mt-2 rounded-full bg-white text-black hover:bg-white/90 h-12 text-base font-semibold"
      >
        {isSubmitting ? (
          <>
            <Icon name="Loader2" size={18} className="animate-spin mr-2" />
            Генерируем ваше КП...
          </>
        ) : (
          "Сгенерировать КП"
        )}
      </Button>
    </form>
  )
}
