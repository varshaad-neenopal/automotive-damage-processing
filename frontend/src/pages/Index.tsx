import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import RepairEstimator from '@/components/estimator/RepairEstimator'

const Index = () => {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    document.title = 'Pavel Motors | AI Repair Estimator'
    const meta = document.querySelector('meta[name="description"]')
    if (meta) meta.setAttribute('content', 'AI-powered car damage repair estimator for dents, scratches and paint work.')
  }, [])

  return (
    <main className="min-h-screen bg-background">
      <header className="container py-16 text-center">
        <h1 className="text-4xl md:text-5xl font-bold tracking-tight mb-4">AI Car Damage Repair Cost Estimator</h1>
        <p className="text-muted-foreground max-w-2xl mx-auto">Upload a photo of the damage and answer a few questions. Our AI assistant will provide an indicative estimate and next steps.</p>
        <div className="mt-8 flex items-center justify-center gap-4">
          <Button variant="ai" size="lg" onClick={() => setOpen(true)}>Start Estimating</Button>
        </div>
      </header>

      <section className="container grid md:grid-cols-3 gap-6 pb-20">
        <Card title="Fast & Accurate" text="Bedrock-powered analysis highlights dents, scratches and paint issues instantly." />
        <Card title="Guided Inputs" text="We ask just what’s needed to refine your estimate without friction." />
        <Card title="Book with Confidence" text="Turn your estimate into a booking with transparent line items." />
      </section>

      <RepairEstimator open={open} onOpenChange={setOpen} />
    </main>
  )
}

function Card({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-lg border p-6 bg-card shadow-sm hover:shadow-md transition-shadow">
      <h2 className="text-lg font-semibold mb-2">{title}</h2>
      <p className="text-sm text-muted-foreground">{text}</p>
    </div>
  )
}

export default Index;
