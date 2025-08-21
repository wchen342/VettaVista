import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { ZoomIn, ZoomOut, RotateCcw } from 'lucide-react'
import * as pdfjsLib from 'pdfjs-dist'

// Set worker path to bundled worker
pdfjsLib.GlobalWorkerOptions.workerSrc = '/editor/pdf.worker.bundle.js'

interface PDFPreviewProps {
    previewData: string
}

export function PDFPreview({ previewData }: PDFPreviewProps) {
    const [scale, setScale] = useState(1)
    const containerRef = useRef<HTMLDivElement>(null)

    const handleZoom = (delta: number) => {
        setScale(prev => Math.max(0.5, Math.min(3, prev + delta)))
    }

    useEffect(() => {
        if (!previewData || !containerRef.current) return

        const renderPDF = async () => {
            try {
                const pdfData = atob(previewData)
                const loadingTask = pdfjsLib.getDocument({ data: pdfData })
                const pdf = await loadingTask.promise
                const container = containerRef.current
                if (!container) return

                container.innerHTML = '' // Clear previous content
                container.className = 'flex flex-col items-center bg-gray-200 min-h-full'

                for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
                    const page = await pdf.getPage(pageNum)
                    const pageContainer = document.createElement('div')
                    pageContainer.className = 'bg-white shadow-lg mb-4 p-2'
                    container.appendChild(pageContainer)

                    const canvas = document.createElement('canvas')
                    canvas.className = 'border border-gray-300'
                    pageContainer.appendChild(canvas)
                    
                    const viewport = page.getViewport({ scale })
                    canvas.width = viewport.width
                    canvas.height = viewport.height
                    
                    const context = canvas.getContext('2d')
                    if (!context) continue

                    await page.render({
                        canvasContext: context,
                        viewport
                    }).promise
                }
            } catch (error) {
                console.error('Error rendering PDF:', error)
            }
        }

        renderPDF()
    }, [previewData, scale])

    return (
        <div className="w-1/2 border-l overflow-hidden flex flex-col bg-gray-200">
            <div className="p-2 border-b bg-white flex items-center justify-end gap-2">
                <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleZoom(-0.25)}
                    disabled={scale <= 0.5}
                >
                    <ZoomOut className="h-4 w-4" />
                </Button>
                <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setScale(1)}
                >
                    <RotateCcw className="h-4 w-4" />
                </Button>
                <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleZoom(0.25)}
                    disabled={scale >= 3}
                >
                    <ZoomIn className="h-4 w-4" />
                </Button>
                <span className="text-sm text-muted-foreground">
                    {Math.round(scale * 100)}%
                </span>
            </div>
            <div className="flex-1 p-4 overflow-auto">
                <div ref={containerRef} />
            </div>
        </div>
    )
} 