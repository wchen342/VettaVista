import { useState, useEffect } from 'react'
import { ApplicationEditor } from './components/ApplicationEditor'

function App() {
    const [sessionId, setSessionId] = useState<string>('')
    const [error, setError] = useState<string>('')

    useEffect(() => {
        // Get session ID from URL
        const params = new URLSearchParams(window.location.search)
        const session = params.get('session')
        
        if (!session) {
            setError('Invalid session - please start the application process again')
            return
        }
        
        setSessionId(session)
    }, [])

    const handleSubmit = async (data: string): Promise<void> => {
        try {
            const response = await fetch('/api/editor/finalize', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    session_id: sessionId,
                    content: data
                }),
            })
            if (!response.ok) {
                throw new Error('Failed to submit')
            }
        } catch (error) {
            console.error('Error submitting:', error)
        }
    }

    if (error) {
        return (
            <div className="w-[95%] mx-auto py-8">
                <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative" role="alert">
                    <strong className="font-bold">Error:</strong>
                    <span className="block sm:inline"> {error}</span>
                </div>
            </div>
        )
    }

    if (!sessionId) {
        return <div>Invalid session</div>
    }

    return (
        <div className="w-[95%] mx-auto py-8">
            <ApplicationEditor
                sessionId={sessionId}
                onSubmit={handleSubmit}
            />
        </div>
    )
}

export default App