import {useCallback, useEffect, useState, useRef} from 'react'
import {Button} from '@/components/ui/button'
import {Eye, EyeOff, Lightbulb, ZoomIn, ZoomOut, RotateCcw} from 'lucide-react'
import {DiffEditor} from '@monaco-editor/react'
import {motion} from 'framer-motion'
import {MessageType, ServerMessage, EditorUpdate} from '../types/editor'
import * as pdfjsLib from 'pdfjs-dist'
import { PDFPreview } from './PDFPreview'

// Set worker path to bundled worker
pdfjsLib.GlobalWorkerOptions.workerSrc = '/editor/pdf.worker.bundle.js'

interface ResumeEditorProps {
    sessionId: string
    content: string
    onSubmit: (content: string) => Promise<void>
    onMessage: (message: ServerMessage) => void
}

export function ResumeEditor({ sessionId, content, onSubmit, onMessage }: ResumeEditorProps) {
    const [originalContent, setOriginalContent] = useState('')
    const [modifiedContent, setModifiedContent] = useState(content)
    const [previewData, setPreviewData] = useState<string | null>(null)
    const [showPreview, setShowPreview] = useState(false)
    const [recommendedSkills, setRecommendedSkills] = useState<string[]>([])
    const [socket, setSocket] = useState<WebSocket | null>(null)

    // Initialize WebSocket connection
    useEffect(() => {
        if (!sessionId) return;  // Don't connect if no session ID

        document.title = 'Resume Editor';

        const ws = new WebSocket(`ws://${window.location.hostname}:${window.location.port}/ws/editor/${sessionId}`)
        
        ws.onmessage = (event: MessageEvent<string>) => {
            try {
                const message = JSON.parse(event.data) as ServerMessage
                onMessage(message)
                
                handleWebSocketMessage(message)
            } catch (error) {
                console.error('Error processing WebSocket message:', error)
            }
        }

        ws.onclose = () => {
            console.log('WebSocket connection closed')
            setSocket(null)
        }

        setSocket(ws)

        return () => {
            ws.close()
        }
    }, [sessionId, onMessage])

    const sendUpdate = useCallback((latex: string) => {
        if (socket?.readyState === WebSocket.OPEN) {
            const update: EditorUpdate = {
                session_id: sessionId,
                new_value: latex
            }
            socket.send(JSON.stringify(update))
        }
    }, [socket, sessionId])

    const handleWebSocketMessage = (message: ServerMessage) => {
        if (message.type === MessageType.INIT && message.phase_data) {
            setOriginalContent(message.phase_data.original)
            setModifiedContent(message.phase_data.customized)
            if (message.phase_data.preview_data) {
                setPreviewData(message.phase_data.preview_data)
            }
            if (message.phase_data.recommended_skills) {
                setRecommendedSkills(message.phase_data.recommended_skills)
            }
        } else if (message.type === MessageType.UPDATE && message.phase_data) {
            if (message.phase_data.customized) {
                setModifiedContent(message.phase_data.customized)
            }
            if (message.phase_data.preview_data) {
                setPreviewData(message.phase_data.preview_data)
            }
        }
    }

    return (
        <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="w-[95%] mx-auto p-4 space-y-4 h-screen flex flex-col"
        >
            <div className="flex justify-between items-center p-4 border-b">
                <h2 className="text-lg font-semibold">Resume Editor</h2>
                <div className="flex gap-2">
                    <Button 
                        variant="outline" 
                        onClick={() => setShowPreview(!showPreview)}
                        disabled={!previewData}
                    >
                        {showPreview ? <EyeOff className="h-4 w-4 mr-1" /> : <Eye className="h-4 w-4 mr-1" />}
                        {showPreview ? 'Hide Preview' : 'Show Preview'}
                    </Button>
                    <Button variant="outline" onClick={() => sendUpdate(modifiedContent)}>
                        Generate PDF
                    </Button>
                    <Button variant="default" onClick={() => void onSubmit(modifiedContent)}>
                        Save and continue
                    </Button>
                </div>
            </div>

            {recommendedSkills.length > 0 && (
                <div className="bg-muted/50 rounded-lg p-4 flex items-start space-x-3">
                    <Lightbulb className="h-5 w-5 text-yellow-500 mt-0.5" />
                    <div>
                        <h3 className="font-medium mb-1">Recommended Skills</h3>
                        <div className="flex flex-wrap gap-2">
                            {recommendedSkills.map((skill, index) => (
                                <span 
                                    key={index}
                                    className="bg-muted px-2 py-1 rounded-md text-sm"
                                >
                                    {skill}
                                </span>
                            ))}
                        </div>
                    </div>
                </div>
            )}

            <div className="flex-1 overflow-hidden flex">
                <div className={`flex-1 ${showPreview ? 'w-1/2' : 'w-full'}`}>
                    <DiffEditor
                        height="100%"
                        original={originalContent}
                        modified={modifiedContent}
                        language="latex"
                        onMount={(editor) => {
                            editor.getModifiedEditor().onDidChangeModelContent(() => {
                                const newValue = editor.getModifiedEditor().getValue()
                                setModifiedContent(newValue)
                                sendUpdate(newValue)
                            })
                            editor.getModel()?.original.updateOptions({ tabSize: 2 })
                            editor.getModel()?.modified.updateOptions({ tabSize: 2 })
                        }}
                        options={{
                            renderSideBySide: true,
                            wordWrap: 'on',
                            minimap: { enabled: false },
                            scrollBeyondLastLine: false,
                            diffWordWrap: 'on',
                            originalEditable: false,
                            readOnly: false
                        }}
                    />
                </div>
                {showPreview && previewData && (
                    <PDFPreview previewData={previewData} />
                )}
            </div>
        </motion.div>
    )
}