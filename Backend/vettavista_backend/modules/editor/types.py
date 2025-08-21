from dataclasses import dataclass
from typing import Optional, Dict, List
from enum import Enum

from vettavista_backend.modules.models.services import ApplicationPhase


class MessageType(str, Enum):
    INIT = "init"
    UPDATE = "update"
    ERROR = "error"
    PHASE_CHANGE = "phase_change"

@dataclass
class EditorUpdate:
    """Editor update data (client to server)"""
    session_id: str
    new_value: str

@dataclass
class PhaseData:
    """Phase data for resume or cover letter"""
    original: str
    customized: str
    preview_data: Optional[str] = None  # Base64 encoded PNG data
    recommended_skills: Optional[List[str]] = None

@dataclass
class ServerMessage:
    """Server to client message"""
    type: MessageType
    error_message: Optional[str] = None
    phase: Optional[ApplicationPhase] = None
    phase_data: Optional[PhaseData] = None

@dataclass
class EditorResponse:
    """Response to an editor update"""
    success: bool
    error_message: Optional[str] = None 