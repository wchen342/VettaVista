import { Editor } from '@monaco-editor/react'
import { Button } from '@/components/ui/button'
import { useState, useEffect } from 'react'
import { ServerMessage, EditorUpdate } from '../types/editor'
import { MessageType } from '../types/editor'
import { Eye, EyeOff } from 'lucide-react'
import { motion } from 'framer-motion'
import { PDFPreview } from './PDFPreview'

interface CoverLetterEditorProps {
    sessionId: string
    content: string
    onSubmit: (content: string) => Promise<void>
    onMessage: (message: ServerMessage) => void
    onBack: () => void
}

export function CoverLetterEditor({ sessionId, content, onSubmit, onMessage, onBack }: CoverLetterEditorProps) {
    const [value, setValue] = useState(content)
    const [showPreview, setShowPreview] = useState(false)
    const [previewData, setPreviewData] = useState<string | null>(null)
    const [socket, setSocket] = useState<WebSocket | null>(null)

    useEffect(() => {
        if (!sessionId) return;  // Don't connect if no session ID

        document.title = 'Cover Letter Editor';

        // Initialize WebSocket connection
        const ws = new WebSocket(`ws://${window.location.hostname}:${window.location.port}/ws/editor/${sessionId}`)
        setSocket(ws)

        ws.onmessage = (event) => {
            const message = JSON.parse(event.data) as ServerMessage
            handleWebSocketMessage(message)
        }

        // Cleanup on unmount
        return () => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.close()
            }
        }
    }, [sessionId])

    const handleWebSocketMessage = (message: ServerMessage) => {
        if (message.type === MessageType.PHASE_CHANGE && message.phase === 'cover_letter' && message.phase_data) {
            // Only set initial value when we get the phase change message
            setValue(message.phase_data.customized)
            setPreviewData(message.phase_data.preview_data || null)
        } else if (message.type === MessageType.UPDATE && message.phase_data) {
            setValue(message.phase_data.customized)
            setPreviewData(message.phase_data.preview_data || null)
        }
        onMessage(message)
    }

    const handleGeneratePDF = () => {
        if (socket?.readyState === WebSocket.OPEN) {
            const update: EditorUpdate = {
                session_id: sessionId,
                new_value: value
            }
            socket.send(JSON.stringify(update))
        }
    }

    const handleSave = async () => {
        if (confirm('Are you sure you want to finalize the cover letter?')) {
            await onSubmit(value)
            window.close()
        }
    }

    const handleBack = async () => {
        try {
            const response = await fetch(`/api/editor/back-to-resume/${sessionId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });
            
            if (!response.ok) {
                throw new Error('Failed to return to resume phase');
            }
            
            onBack();
        } catch (error) {
            console.error('Error returning to resume phase:', error);
        }
    };

    return (
        <div className="w-[95%] mx-auto p-4 h-screen flex flex-col">
            <div className="flex justify-between items-center p-4 border-b">
                <h2 className="text-lg font-semibold">Cover Letter Editor</h2>
                <div className="flex gap-2">
                    <Button variant="outline" onClick={handleBack}>
                        Back to Resume
                    </Button>
                    <Button 
                        variant="outline" 
                        onClick={() => setShowPreview(!showPreview)}
                        disabled={!previewData}
                    >
                        {showPreview ? <EyeOff className="h-4 w-4 mr-1" /> : <Eye className="h-4 w-4 mr-1" />}
                        {showPreview ? 'Hide Preview' : 'Show Preview'}
                    </Button>
                    <Button variant="outline" onClick={handleGeneratePDF}>
                        Generate PDF
                    </Button>
                    <Button variant="default" onClick={handleSave}>
                        Save and continue
                    </Button>
                </div>
            </div>
            
            <div className="flex-1 overflow-hidden flex w-[95%] mx-auto">
                <div className={`flex-1 ${showPreview ? 'w-1/2' : 'w-full'}`}>
                    <Editor
                        height="100%"
                        language="latex"
                        value={value}
                        onChange={(newValue) => setValue(newValue || '')}
                        options={{
                            wordWrap: 'on',
                            minimap: { enabled: false },
                            scrollBeyondLastLine: false
                        }}
                    />
                </div>
                {showPreview && previewData && (
                    <PDFPreview previewData={previewData} />
                )}
            </div>
        </div>
    )
} 