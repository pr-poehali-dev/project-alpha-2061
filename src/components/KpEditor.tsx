import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { useToast } from "@/hooks/use-toast"
import Icon from "@/components/ui/icon"

const SUBMISSIONS_URL = "https://functions.poehali.dev/7ce7a415-986b-4b02-89ac-6c6edcf527a7"

export interface KpSection {
  title: string
  description: string
  image_url?: string
}

export interface GeneratedContent {
  title: string
  subtitle: string
  sections: KpSection[]
  colors: {
    primary: string
    secondary: string
    accent: string
  }
  font: string
}

interface KpEditorProps {
  submissionId: number
  initialContent: GeneratedContent
  initialTelegramContact?: string
}

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

export default function KpEditor({ submissionId, initialContent, initialTelegramContact }: KpEditorProps) {
  const { toast } = useToast()
  const [content, setContent] = useState<GeneratedContent>(initialContent)
  const [telegramContact, setTelegramContact] = useState(initialTelegramContact || "")
  const [isSaving, setIsSaving] = useState(false)
  const [isSending, setIsSending] = useState(false)
  const [isSent, setIsSent] = useState(false)
  const [showSendForm, setShowSendForm] = useState(false)
  const [uploadingIndex, setUploadingIndex] = useState<number | null>(null)

  useEffect(() => {
    const fontName = content.font?.replace(/\s+/g, "+") || "Inter"
    const linkId = "kp-editor-font"
    let link = document.getElementById(linkId) as HTMLLinkElement | null
    if (!link) {
      link = document.createElement("link")
      link.id = linkId
      link.rel = "stylesheet"
      document.head.appendChild(link)
    }
    link.href = `https://fonts.googleapis.com/css2?family=${fontName}:wght@400;600;700&display=swap`
  }, [content.font])

  const saveContent = async (updated: GeneratedContent) => {
    setContent(updated)
    setIsSaving(true)
    try {
      await fetch(`${SUBMISSIONS_URL}?action=update`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: submissionId, generated_content: updated }),
      })
    } catch {
      // silent autosave failure
    } finally {
      setIsSaving(false)
    }
  }

  const updateField = (field: "title" | "subtitle", value: string) => {
    saveContent({ ...content, [field]: value })
  }

  const updateColor = (key: "primary" | "secondary" | "accent", value: string) => {
    saveContent({ ...content, colors: { ...content.colors, [key]: value } })
  }

  const updateSection = (index: number, field: "title" | "description", value: string) => {
    const sections = [...content.sections]
    sections[index] = { ...sections[index], [field]: value }
    saveContent({ ...content, sections })
  }

  const handleImageUpload = async (index: number, file: File) => {
    setUploadingIndex(index)
    try {
      const data = await fileToBase64(file)
      const response = await fetch(`${SUBMISSIONS_URL}?action=upload_image`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          image_file: {
            filename: file.name,
            content_type: file.type || "image/png",
            data,
          },
        }),
      })
      const result = await response.json()
      const sections = [...content.sections]
      sections[index] = { ...sections[index], image_url: result.url }
      await saveContent({ ...content, sections })
    } catch {
      toast({ title: "Не удалось загрузить фото", variant: "destructive" })
    } finally {
      setUploadingIndex(null)
    }
  }

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

  const { primary, secondary, accent } = content.colors

  return (
    <div className="fixed inset-0 z-[10000] overflow-y-auto bg-black">
      <div
        className="min-h-screen w-full py-16 px-5 sm:px-10"
        style={{
          background: `linear-gradient(160deg, ${secondary} 0%, ${primary} 100%)`,
          fontFamily: `'${content.font || "Inter"}', sans-serif`,
        }}
      >
        <div className="max-w-3xl mx-auto flex flex-col gap-10 text-white">
          <div className="flex items-center justify-between gap-4">
            <span className="text-sm text-white/60">
              {isSaving ? "Сохраняем..." : "Изменения сохраняются автоматически"}
            </span>
            <div className="flex items-center gap-2">
              {(["primary", "secondary", "accent"] as const).map((key) => (
                <label key={key} className="relative w-8 h-8 rounded-full border-2 border-white/40 overflow-hidden cursor-pointer" style={{ background: content.colors[key] }}>
                  <input
                    type="color"
                    value={content.colors[key]}
                    onChange={(e) => updateColor(key, e.target.value)}
                    className="absolute inset-0 opacity-0 cursor-pointer"
                  />
                </label>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-4">
            <Textarea
              value={content.title}
              onChange={(e) => setContent({ ...content, title: e.target.value })}
              onBlur={(e) => updateField("title", e.target.value)}
              className="bg-transparent border-none text-4xl sm:text-6xl font-bold resize-none p-0 text-white focus-visible:ring-0 leading-tight"
              rows={2}
            />
            <Textarea
              value={content.subtitle}
              onChange={(e) => setContent({ ...content, subtitle: e.target.value })}
              onBlur={(e) => updateField("subtitle", e.target.value)}
              className="bg-transparent border-none text-lg sm:text-xl text-white/80 resize-none p-0 focus-visible:ring-0"
              rows={2}
            />
          </div>

          <div className="flex flex-col gap-6">
            {content.sections.map((section, index) => (
              <div
                key={index}
                className="rounded-2xl border border-white/20 bg-white/10 backdrop-blur-md p-6 flex flex-col gap-4"
                style={{ borderColor: `${accent}66` }}
              >
                {section.image_url ? (
                  <img src={section.image_url} alt="" className="w-full h-48 object-cover rounded-xl" />
                ) : null}

                <label className="flex items-center gap-2 text-sm text-white/60 cursor-pointer w-fit">
                  <Icon name={uploadingIndex === index ? "Loader2" : "ImagePlus"} size={16} className={uploadingIndex === index ? "animate-spin" : ""} />
                  {section.image_url ? "Заменить фото" : "Добавить фото"}
                  <input
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={(e) => {
                      const file = e.target.files?.[0]
                      if (file) handleImageUpload(index, file)
                    }}
                  />
                </label>

                <Input
                  value={section.title}
                  onChange={(e) => {
                    const sections = [...content.sections]
                    sections[index] = { ...sections[index], title: e.target.value }
                    setContent({ ...content, sections })
                  }}
                  onBlur={(e) => updateSection(index, "title", e.target.value)}
                  style={{ color: accent }}
                  className="bg-transparent border-none text-xl font-semibold p-0 focus-visible:ring-0"
                />
                <Textarea
                  value={section.description}
                  onChange={(e) => {
                    const sections = [...content.sections]
                    sections[index] = { ...sections[index], description: e.target.value }
                    setContent({ ...content, sections })
                  }}
                  onBlur={(e) => updateSection(index, "description", e.target.value)}
                  className="bg-transparent border-none text-white/80 resize-none p-0 focus-visible:ring-0"
                  rows={3}
                />
              </div>
            ))}
          </div>

          <div className="flex justify-center pt-6">
            {isSent ? (
              <div className="flex flex-col items-center gap-3 text-center">
                <div className="w-16 h-16 rounded-full bg-green-500/20 flex items-center justify-center">
                  <Icon name="Check" size={32} className="text-green-400" />
                </div>
                <p className="text-white/80">Заявка отправлена, мы свяжемся с вами в Telegram</p>
              </div>
            ) : showSendForm ? (
              <div className="w-full max-w-sm flex flex-col gap-3 rounded-2xl border border-white/20 bg-white/10 backdrop-blur-md p-6">
                <Label className="text-white/90">Ваш Telegram или номер</Label>
                <Input
                  value={telegramContact}
                  onChange={(e) => setTelegramContact(e.target.value)}
                  placeholder="@username или +7 999 000-00-00"
                  className="bg-white/10 border-white/20 text-white placeholder:text-white/40"
                />
                <Button
                  onClick={handleSend}
                  disabled={isSending}
                  className="rounded-full bg-white text-black hover:bg-white/90 h-11 font-semibold"
                >
                  {isSending ? (
                    <>
                      <Icon name="Loader2" size={18} className="animate-spin mr-2" />
                      Отправляем...
                    </>
                  ) : (
                    "Подтвердить и отправить"
                  )}
                </Button>
              </div>
            ) : (
              <Button
                onClick={() => setShowSendForm(true)}
                className="rounded-full bg-white text-black hover:bg-white/90 h-14 px-10 text-lg font-semibold"
              >
                <Icon name="Send" size={20} className="mr-2" />
                Отправить в Telegram
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
