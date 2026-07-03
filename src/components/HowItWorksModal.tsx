import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import Icon from "@/components/ui/icon"

interface HowItWorksModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const steps = [
  {
    icon: "FileText",
    title: "Загрузите своё КП",
    description: "Прикрепите файл вашего текущего коммерческого предложения — мы возьмём из него всю нужную информацию.",
  },
  {
    icon: "Sparkles",
    title: "Покажите желаемый дизайн",
    description: "Загрузите пример КП, дизайн которого вам нравится — наш ИИ проанализирует стиль, цвета и структуру.",
  },
  {
    icon: "Wand2",
    title: "Получите готовый результат",
    description: "За пару минут мы соберём новое красивое КП с вашими данными в понравившемся дизайне — останется только отредактировать текст и отправить.",
  },
]

export default function HowItWorksModal({ open, onOpenChange }: HowItWorksModalProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[#0f1629]/95 border-white/20 text-white backdrop-blur-md max-w-lg w-full rounded-3xl">
        <DialogHeader>
          <DialogTitle className="text-2xl font-semibold text-white text-center">
            Как это работает
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-5 mt-2">
          {steps.map((step, index) => (
            <div key={index} className="flex items-start gap-4">
              <div className="w-11 h-11 rounded-full bg-white/10 border border-white/20 flex items-center justify-center shrink-0">
                <Icon name={step.icon} size={20} className="text-white" />
              </div>
              <div className="flex flex-col gap-1">
                <h4 className="font-semibold text-white">
                  {index + 1}. {step.title}
                </h4>
                <p className="text-sm text-white/70">{step.description}</p>
              </div>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}
