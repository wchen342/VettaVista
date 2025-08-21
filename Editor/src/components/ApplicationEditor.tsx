import { useState } from 'react'
import { ResumeEditor } from './ResumeEditor'
import { CoverLetterEditor } from './CoverLetterEditor'
import { MessageType, ServerMessage } from '../types/editor'

interface ApplicationEditorProps {
    sessionId: string
    onSubmit: (content: string) => Promise<void>
}

export function ApplicationEditor({ sessionId, onSubmit }: ApplicationEditorProps) {
    const [phase, setPhase] = useState<'resume'|'cover_letter'>('resume')
    const [resumeContent, setResumeContent] = useState('')
    const [coverLetterContent, setCoverLetterContent] = useState('')

    const handleWebSocketMessage = (message: ServerMessage) => {
        if (message.type === MessageType.PHASE_CHANGE && message.phase && message.phase_data) {
            setPhase(message.phase)
            if (message.phase === 'resume') {
                setResumeContent(message.phase_data.customized)
            } else if (message.phase === 'cover_letter') {
                setCoverLetterContent(message.phase_data.customized)
            }
        }
    }

    const handleSubmit = async (content: string) => {
        try {
            const endpoint = phase === 'resume' 
                ? `/api/apply/cover-letter/${sessionId}`
                : '/api/editor/finalize';
            
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    session_id: sessionId,
                    content
                }),
            });
            
            if (!response.ok) {
                throw new Error('Failed to submit');
            }
        } catch (error) {
            console.error('Error submitting:', error);
        }
    };

    return (
        <>
            {phase === 'resume' && (
                <ResumeEditor
                    sessionId={sessionId}
                    content={resumeContent}
                    onSubmit={handleSubmit}
                    onMessage={handleWebSocketMessage}
                />
            )}
            {phase === 'cover_letter' && (
                <CoverLetterEditor
                    sessionId={sessionId}
                    content={coverLetterContent}
                    onSubmit={handleSubmit}
                    onMessage={handleWebSocketMessage}
                    onBack={() => setPhase('resume')}
                />
            )}
        </>
    )
} 