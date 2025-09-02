import { useIsMobile } from '@/hooks/use-mobile'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Drawer, DrawerContent, DrawerHeader, DrawerTitle } from '@/components/ui/drawer'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from "@/components/ui/textarea";
import { useToast } from '@/hooks/use-toast'
import { analyzeImage, estimateCost, type AnalysisDamage } from '@/lib/estimatorApi'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

interface RepairEstimatorProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

type Step = 'upload' | 'analyzing' | 'details' | 'result' | 'region-blocked' | 'error'

export default function RepairEstimator({ open, onOpenChange }: RepairEstimatorProps) {
  const isMobile = useIsMobile()
  const [step, setStep] = useState<Step>('upload')
  const [images, setImages] = useState<File[]>([])
  const [previews, setPreviews] = useState<string[]>([])
  const [damages, setDamages] = useState<AnalysisDamage[]>([])
  const [noDamageDialogOpen, setNoDamageDialogOpen] = useState(false)
  const [vehicle, setVehicle] = useState({ make: '', model: ''})
  const [originalVehicle, setOriginalVehicle] = useState({ make: '', model: '' });
  const [location, setLocation] = useState('')
  const [loading, setLoading] = useState(false)
  const { toast } = useToast()

  const [dialogOpen, setDialogOpen] = useState(false)
  const [name, setName] = useState("")
  const [mobile, setMobile] = useState("")
  const [email, setEmail] = useState("")

  const reset = () => {
    setStep('upload')
    setImages([])                         
    setPreviews([])                       
    setDamages([])                        
    setVehicle({ make: '', model: '' })   
    setLocation('')                       
  }

  useEffect(() => { if (!open) reset() }, [open])

  const handleFiles = (files: FileList) => {
    const totalAfterUpload = images.length + files.length
    if (totalAfterUpload > 8) {
      toast({ title: "Upload limit exceeded", description: "You can upload a maximum of 8 images only." })
      return
    }

    const validFiles: File[] = []
    const urls: string[] = []

    Array.from(files).forEach(file => {
      if (!file.type.startsWith("image/")) {
        toast({ title: "Invalid file", description: "Please upload an image file." })
        return
      }
      if (file.size > 8 * 1024 * 1024) {
        toast({ title: "File too large", description: "Max 8 MB allowed per file." })
        return
      }
      validFiles.push(file)
      urls.push(URL.createObjectURL(file))
    })

    setImages(prev => [...prev, ...validFiles])
    setPreviews(prev => [...prev, ...urls])
  }

  const startAnalyze = async () => {
    if (!images.length) {
      toast({ title: 'Upload required', description: 'Add at least one photo to continue.' })
      return
    }
    if (!location.trim()) {
      toast({ title: 'Location required', description: 'Please enter your city or pincode.' })
      return
    }

    setStep("analyzing")
    setLoading(true)
    try {
      const formData = new FormData()
      images.forEach(img => formData.append("images", img))
      formData.append("meta", JSON.stringify({ location }))

      const res = await fetch("http://fullstack-alb-603933093.us-west-2.elb.amazonaws.com/api/analyze", {
        method: "POST",
        body: formData,
      }).then(r => r.json())

      if (res.isCar === false) {
        setDialogOpen(true)
        return
      }

      if (res.isCar && (!res.detectedDamages?.length && (!res.visible_damage || res.visible_damage.length === 0))) {
        setNoDamageDialogOpen(true)
        return
      }

      if (!res.regionAvailable) {
        setStep("region-blocked")
        return
      }

      setDamages([{ severity: res.damageSummary }])
      setVehicle({ make: res.brand || "", model: res.model })
      setOriginalVehicle({ make: res.brand || "", model: res.model || "" })
      setStep("details")
    } catch (e) {
      setStep("error")
    } finally {
      setLoading(false)
    }
  }

  function isReadOnlyField(value: string, detected: string) {
    if (!detected || detected.toLowerCase() === "unknown") return false;
    return true;
  }

  const computeEstimate = async () => {
    setLoading(true)
    try {
      setOriginalVehicle({ make: vehicle.make, model: vehicle.model })
      const est = await estimateCost({ damages, vehicle, location })
      setResult(est)
      setStep('result')
    } catch (e) {
      setStep('error')
    } finally {
      setLoading(false)
    }
  }

  const [result, setResult] = useState<Awaited<ReturnType<typeof estimateCost>> | null>(null)

  const Container = isMobile ? Drawer : Dialog
  const Content = isMobile ? DrawerContent : DialogContent
  const Header = isMobile ? DrawerHeader : DialogHeader
  const Title = isMobile ? DrawerTitle : DialogTitle

  return (
    <Container open={open} onOpenChange={onOpenChange}>
      <Content className="max-w-3xl">
        <Header>
          <Title>AI Repair Cost Estimator</Title>
        </Header>

        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Invalid Image</DialogTitle>
            </DialogHeader>
            <p className="text-sm text-muted-foreground">
              Please upload a proper damaged car image to get an estimate.
            </p>
            <DialogFooter>
              <Button
          variant="ai"
          onClick={() => {
            setDialogOpen(false); 
            reset();              
          }}
        >
          Upload Again
        </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={noDamageDialogOpen} onOpenChange={setNoDamageDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>No Damages Detected</DialogTitle>
            </DialogHeader>
            <p className="text-sm text-muted-foreground">
              Try again, please upload a car image that has damages to give an estimate. This car seems quite undamaged.
            </p>
            <DialogFooter>
              <Button
                variant="ai"
                onClick={() => {
                  setNoDamageDialogOpen(false)
                  reset() 
                }}
              >
                Upload Again
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {step === 'upload' && (
          <section className="space-y-4 animate-fade-in">
            <p className="text-sm text-muted-foreground">
              Upload clear photos of the damaged areas. We will analyze dents, scratches and paint issues.
            </p>

            <div
              className="border border-dashed rounded-lg p-6 text-center cursor-pointer hover:bg-accent/30 transition-colors"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault()
                const files = Array.from(e.dataTransfer.files || [])
                if (files.length > 0) handleFiles(files)
              }}
            >
              {previews.length > 0 ? (
                <div className="grid grid-cols-6 gap-3 mt-3">
                  {previews.map((src, idx) => (
                    <div key={idx} className="relative">
                      <img
                        src={src}
                        alt={`preview-${idx}`}
                        className="max-h-40 rounded-md object-contain mx-auto"
                      />
                      <div className="absolute inset-0 ai-scan animate-shimmer rounded-md mix-blend-overlay" />
                    </div>
                  ))}
                </div>

              ) : (
                <>
                  <p className="text-sm">Drag & drop images here, or click to select</p>
                  <div className="mt-3">
                    <Input
                      type="file"
                      accept="image/*"
                      multiple
                      onChange={(e) =>
                        e.target.files && handleFiles(Array.from(e.target.files))
                      }
                    />
                  </div>
                </>
              )}
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <Label htmlFor="location">
                  Your City / Pincode <span style={{ color: 'red' }}>*</span>
                </Label>
                <Input
                  id="location"
                  placeholder="e.g., Bengaluru / 560001"
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  required
                />
              </div>

              <div className="flex items-end">
                <Button
                  variant="ai"
                  className="w-full"
                  onClick={startAnalyze}
                  disabled={images.length === 0} // disable if no images uploaded
                >
                  Analyze Images
                </Button>
              </div>
            </div>
          </section>
        )}


        {/* Analyzing */}
        {step === 'analyzing' && (
          <section className="grid sm:grid-cols-2 gap-6 items-center animate-fade-in">
            <div className="relative">
            {previews.length > 0 && (
                    <img
                      src={previews[0]}   // show first preview
                      alt="preview"
                      className="rounded-md object-contain max-h-72 w-full"
                    />
                  )}              <div className="absolute inset-0 ai-scan animate-shimmer rounded-md" />
            </div>
            <div className="space-y-3">
              <h3 className="text-lg font-medium">Analyzing image</h3>
              <p className="text-sm text-muted-foreground">Detecting dents, scratches, and paint anomalies.
                <span className="inline-flex items-center gap-1 ml-2"><span className="size-2 rounded-full bg-primary animate-dots" />
                </span>
              </p>
              <div className="h-2 rounded-full bg-secondary overflow-hidden">
                <div className="h-full w-full ai-scan animate-shimmer" />
              </div>
            </div>
          </section>
        )}

        {step === 'region-blocked' && (
          <section className="space-y-4 animate-fade-in">
            <h3 className="text-lg font-medium">We are not available in your region yet</h3>
            <p className="text-sm text-muted-foreground">Please share your contact details and we will reach out when service is available.</p>
            <div className="grid sm:grid-cols-3 gap-3">
              <Input placeholder="Name" />
              <Input placeholder="Email" />
              <Input placeholder="Phone" />
            </div>
            <div className="flex gap-3">
              <Button variant="outline" onClick={() => setStep('upload')}>Back</Button>
              <Button onClick={() => { toast({ title: 'Thanks!', description: 'We will notify you.' }); onOpenChange(false) }}>Notify Me</Button>
            </div>
          </section>
        )}

        {step === 'error' && (
          <section className="space-y-4 animate-fade-in">
            <h3 className="text-lg font-medium">Something went wrong</h3>
            <p className="text-sm text-muted-foreground">Please try again or choose a different image.</p>
            <div className="flex gap-3">
              <Button variant="outline" onClick={() => setStep('upload')}>Back</Button>
              <Button variant="ai" onClick={startAnalyze}>Retry</Button>
            </div>
          </section>
        )}

        {step === 'details' && (
          <section className="space-y-6 animate-fade-in">
            <div className="grid sm:grid-cols-2 gap-6">

              <div className="space-y-3">
                <h3 className="font-medium">Detected damages</h3>
                <div className="space-y-2">
                  {damages.map((d, idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      <Textarea
                        value={d.severity || ""}
                        readOnly
                        placeholder="Describe the damage (e.g., Front door dent, deep scratch)"
                        className="min-h-[120px] w-full resize-none bg-gray-100 cursor-not-allowed"
                        rows={9}
                      />
                    </div>
                  ))}
                </div>
              </div>

              <div className="space-y-3">
                <h3 className="font-medium">Vehicle details</h3>
                <div className="grid sm:grid-cols-2 gap-3"> 
                  <div className="col-span-1 w-full">
                    <Label htmlFor="make" className="mb-3 block">
                      Brand {vehicle.make && vehicle.make.toLowerCase() !== "unknown" ? <span className="text-red-500">*</span> : null}
                    </Label>
                    <Input
                      id="make"
                      className={`w-full ${isReadOnlyField(vehicle.make, originalVehicle.make) ? "bg-gray-100 cursor-not-allowed" : "bg-white"}`}
                      value={vehicle.make.toLowerCase() === "unknown" ? "" : vehicle.make}
                      readOnly={isReadOnlyField(vehicle.make, originalVehicle.make)}
                      onChange={(e) => setVehicle({ ...vehicle, make: e.target.value })}
                      placeholder=""
                    />
                  </div>

                  <div className="col-span-1 w-full">
                    <Label htmlFor="model" className="mb-3 block">
                      Model {vehicle.model && vehicle.model.toLowerCase() !== "unknown" ? <span className="text-red-500">*</span> : null}
                    </Label>
                    <Input
                      id="model"
                      className={`w-full ${isReadOnlyField(vehicle.model, originalVehicle.model) ? "bg-gray-100 cursor-not-allowed" : "bg-white"}`}
                      value={vehicle.model.toLowerCase() === "unknown" ? "" : vehicle.model}
                      readOnly={isReadOnlyField(vehicle.model, originalVehicle.model)}
                      onChange={(e) => setVehicle({ ...vehicle, model: e.target.value })}
                      placeholder=""
                    />
                  </div>
                </div>
                <br></br><br></br><br></br>
                <div className="flex gap-3">
                  <Button variant="outline" onClick={() => setStep('upload')}>
                    Back
                  </Button>
                  <Button
                    variant="ai"
                    onClick={computeEstimate}
                    disabled={!damages.length || loading} // disable if loading
                    className={loading ? "opacity-70 cursor-not-allowed blur-[0.5px]" : ""}
                  >
                    {loading ? "Estimating" : "Get Estimate"}
                  </Button>
                </div>
              </div>

            </div>
          </section>
        )}

        {step === 'result' && result && (
          <section className="space-y-6 animate-fade-in">
            <div className="max-h-[350px] overflow-y-auto pr-2">
              <h3 className="font-medium">Indicative Estimate</h3>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="align-middle text-center">S.No</TableHead>
                    <TableHead className="align-middle text-center">Component</TableHead>
                    <TableHead className="align-middle text-center">Description</TableHead>
                    <TableHead className="align-middle text-center w-[120px]">
                      Cost (INR)
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {result.items.map((it, i) => (
                    <TableRow key={i}>
                      <TableCell className="text-left">{i + 1}</TableCell>
                      <TableCell className="text-left">{it["Component"]}</TableCell>
                      <TableCell className="text-left">{it["Description"]}</TableCell>
                      <TableCell className="text-left w-[120px]">
                        {result.currency} {it["Cost (INR)"].toLocaleString()}
                      </TableCell>
                    </TableRow>
                  ))}
                  <TableRow>
                    <TableCell colSpan={3} className="text-left font-semibold">
                      Estimated Total
                    </TableCell>
                    <TableCell className="text-left font-semibold w-[120px]">
                      {result.currency} {result.total.toLocaleString()}
                    </TableCell>
                  </TableRow>
                </TableBody>
              </Table>

            </div>

            {result.paragraphs?.map((p, idx) => {
              if (p.startsWith("Disclaimer:")) {
                const [boldPart, rest] = p.split(":"); // Split at first colon
                return (
                  <p key={idx} className="text-sm text-muted-foreground">
                    <span className="font-bold">{boldPart}:</span>{" "}
                    {rest?.includes("please") ? (
                      <>
                        {rest.split("please")[0]}{" "}
                        <a
                          href="https://www.pavelmotors.com/contact-us"
                          target="_blank"
                          className="text-blue-500 underline"
                        >
                          please contact us
                        </a>
                      </>
                    ) : (
                      rest
                    )}
                  </p>
                );
              } else if (p.startsWith("NOTE:")) {
                return (
                  <p key={idx} className="text-sm text-muted-foreground font-bold">
                    {p}
                  </p>
                );
              } else {
                return (
                  <p key={idx} className="text-sm text-muted-foreground">
                    {p}
                  </p>
                );
              }
            })}

            <div className="flex gap-3">
              <Button variant="outline" onClick={() => setStep('details')}>Edit details</Button>
              <Button onClick={() => setDialogOpen(true)}>
                Book Service
              </Button>
            </div>

            {/* Popup Dialog */}
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Enter your details</DialogTitle>
                </DialogHeader>

                <div className="space-y-4">
                  <div>
                    <Label htmlFor="name">Name <span className="text-red-500">*</span></Label>
                    <Input id="name" value={name} onChange={(e) => setName(e.target.value)} required />
                  </div>
                  <div>
                    <Label htmlFor="mobile">Mobile <span className="text-red-500">*</span></Label>
                    <Input id="mobile" value={mobile} onChange={(e) => setMobile(e.target.value)} required />
                  </div>
                  <div>
                    <Label htmlFor="email">Email (optional)</Label>
                    <Input id="email" value={email} onChange={(e) => setEmail(e.target.value)} />
                  </div>
                </div>

                <DialogFooter>
                  <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancel</Button>
                    <Button
                      onClick={async () => {
                        if (!name || !mobile) {
                          toast({ title: "Missing info", description: "Name and Mobile are required." })
                          return
                        }

                        try {
                          const subject = `Booking Request Received – ${vehicle.make} ${vehicle.model}`

                          // Build the estimate table
                          const items = result?.items ?? []
                          const rowsHtml = items.map((it, idx) => {
                            const cost = Number(it["Cost (INR)"] ?? 0).toLocaleString("en-IN")
                            return `
                              <tr>
                                <td>${idx + 1}</td>
                                <td>${it["Component"] ?? ""}</td>
                                <td>${it["Description"] ?? ""}</td>
                                <td style="text-align:right;">${result?.currency ?? "₹"} ${cost}</td>
                              </tr>
                            `
                          }).join("")

                          const totalRow = result
                            ? `
                              <tr>
                                <td colspan="3" style="text-align:left; font-weight:600;">Estimated Total</td>
                                <td style="text-align:right; font-weight:600;">
                                  ${result.currency} ${Number(result.total ?? 0).toLocaleString("en-IN")}
                                </td>
                              </tr>
                            `
                            : ""

                          const estimateTable = items.length
                            ? `
                              <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse; font-family:Arial, sans-serif; font-size:14px; width:100%;">
                                <thead style="background-color:#f9f9f9;">
                                  <tr>
                                    <th style="text-align:left;">S. No</th>
                                    <th style="text-align:left;">Component</th>
                                    <th style="text-align:left;">Description</th>
                                    <th style="text-align:right;">Cost (INR)</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  ${rowsHtml}
                                  ${totalRow}
                                </tbody>
                              </table>
                            `
                            : `<p><i>No estimate data available.</i></p>`

                          // const emailLine = email.trim() ? `<li><b>Email:</b> ${email.trim()}</li>` : ""
                          const emailLine = email.trim() ? `<p><b>Email:</b> ${email.trim()}</p>` : "";
                          const damageSummary = damages.map((d, i) => `<li>${d.severity}</li>`).join("")
                          const emailBody = `
                            <p>Dear Service Lead,</p>
                            <p>A new <b>service booking request</b> has been submitted. Please find the details below:</p>

                            <h3>Customer Information</h3>
                            <p>
                              <b>Name:</b> ${name}<br>
                              <b>Mobile:</b> ${mobile}<br>
                              ${emailLine}
                            </p>
                            <h3 id="vehicle-info-marker">Vehicle Information</h3>   
                            <div><b>Make & Model:</b> ${vehicle.make} ${vehicle.model}</div>
                          <div><b>Location:</b> ${location}</div>
                            <p>
                            <b>Detected Damages Summary:</b> ${damageSummary}<br>
                              <b>Estimated Repair Cost for the attached damaged car image:</b> ${estimateTable}<br>
                            </p>


                            <p style="margin-top:16px;">Please reach out to the customer to proceed with the booking.</p>
                            <p>Best regards,<br/><b>Pavel Motors</b></p>
                          `
                          // 🔹 Use FormData 
                          const formData = new FormData()
                          formData.append("to", "dhruv.chowdary@neenopal.com")
                          formData.append("subject", subject)
                          formData.append("body", emailBody)

                          if (images && images.length > 0) {  
                images.forEach((img) => {
                  formData.append("images", img)   
                })
              }

                          await fetch("http://fullstack-alb-603933093.us-west-2.elb.amazonaws.com/api/send-email", {
                            method: "POST",
                            body: formData,  
                          })

                          setDialogOpen(false)
                          onOpenChange(false)
                          toast({
                            title: "Booking confirmed",
                            description: "We have sent your booking details via email."
                          })
                        } catch (err) {
                          toast({ title: "Error", description: "Failed to send email." })
                        }
                      }}
                    >
                      Submit
                    </Button>
                </DialogFooter>

              </DialogContent>
            </Dialog>
          </section>
        )}
      </Content>
    </Container>
  )

  function updateDamage(index: number, patch: Partial<AnalysisDamage>) {
    setDamages((prev) => prev.map((d, i) => (i === index ? { ...d, ...patch } : d)))
  }
}
