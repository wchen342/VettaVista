// Matches Python's MessageType enum
export enum MessageType {
    INIT = 'init',
    UPDATE = 'update',
    ERROR = 'error',
    PHASE_CHANGE = 'phase_change'
}

// Client -> Server message (matches Python's EditorUpdate)
export interface EditorUpdate {
    session_id: string;
    new_value: string;
}

// Server -> Client message (matches Python's ServerMessage)
export interface ServerMessage {
    type: MessageType;
    error_message?: string;
    phase?: 'resume'|'cover_letter';
    phase_data?: {
        original: string
        customized: string
        preview_data?: string
        recommended_skills?: string[]
    }
} 