  export type DamageType = 'dent' | 'scratch' | 'paint' | 'crack'

  export interface AnalysisDamage {
    type: DamageType
    severity: 'low' | 'medium' | 'high'
    panel?: string
  }

  export interface AnalysisResponse {
    detectedDamages: AnalysisDamage[]
    regionAvailable: boolean
    notes?: string
    isCar: boolean
    brand?: string
    model?: string
    visible_damage?: AnalysisDamage[]   
    summary?: string
  }

    export interface EstimateItem {
    component: string
    description: number
    cost: number
  }

  export interface EstimateResponse {
    currency: string
    items: EstimateItem[]
    total: number
    paragraphs?: string[]
  }

  const DEFAULT_BASE = 'http://fullstack-alb-603933093.us-west-2.elb.amazonaws.com/api'

  const BASE_URL: string = (globalThis as any).PAVEL_API_BASE || DEFAULT_BASE

  export async function analyzeImage(file: File, extra: Record<string, any>): Promise<AnalysisResponse> {
    const fd = new FormData()
    fd.append('image', file)
    fd.append('meta', JSON.stringify(extra))

    try {
      const res = await fetch(`${BASE_URL}/analyze`, { method: 'POST', body: fd })
      if (!res.ok) throw new Error('Bad response')
      return (await res.json()) as AnalysisResponse
    } catch (e) {
      const location = String(extra?.location || '').toLowerCase()
      const regionAvailable = !(location.includes('usa') || location.includes('uk'))
      return {
        regionAvailable,
        detectedDamages: [
          { type: 'dent', severity: 'medium', panel: 'front door' },
          { type: 'scratch', severity: 'low', panel: 'rear bumper' },
        ],
        notes: 'Sample analysis (offline fallback). Connect AWS backend to enable real Bedrock insights.'
      }
    }
  }

export async function estimateCost(payload: {
  damages: AnalysisDamage[];
  vehicle: { make?: string; model?: string };
  location?: string;
}): Promise<EstimateResponse> {
  try {
    const res = await fetch(`${BASE_URL}/estimate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        brand: payload.vehicle.make,
        model: payload.vehicle.model,
        location: payload.location,
        visible_damage: payload.damages,
      }),
    });

    if (!res.ok) throw new Error("Bad response");
    const data = await res.json();
    console.log("Estimate API response:", data); 
    return data as EstimateResponse;
  } catch (e) {
    return {
      currency: "INR",
      items: [],
      total: 0,
      paragraphs: [
        "Disclaimer: Please note that this estimate is based on inputs received. For a more detailed & accurate estimate, https://www.pavelmotors.com/contact-us"
      ]
    };
  }
}
