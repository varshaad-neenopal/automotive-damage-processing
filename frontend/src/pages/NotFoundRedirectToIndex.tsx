import { useEffect, useState } from 'react'
import RepairEstimator from '@/components/estimator/RepairEstimator'

// This page exists only to open the Estimator immediately while adding SEO
const NotFoundRedirectToIndex = () => {
  const [open, setOpen] = useState(true)

  useEffect(() => {
    document.title = 'AI Car Damage Repair Cost Estimator | Pavel Motors'
    const metaDesc = document.querySelector('meta[name="description"]')
    if (metaDesc) metaDesc.setAttribute('content', 'Upload a photo of car damage and get an instant, AI-assisted repair estimate for dents and scratches.')

    // canonical tag
    let link = document.querySelector('link[rel="canonical"]') as HTMLLinkElement | null
    if (!link) {
      link = document.createElement('link')
      link.rel = 'canonical'
      document.head.appendChild(link)
    }
    link.href = window.location.origin + '/estimate'
  }, [])

  return (
    <div className="min-h-screen flex items-center justify-center">
      <RepairEstimator open={open} onOpenChange={(o) => setOpen(o)} />
    </div>
  )
}

export default NotFoundRedirectToIndex
