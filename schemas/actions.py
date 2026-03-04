from enum import Enum
from typing import Optional
from pydantic import BaseModel
from datetime import datetime

class ActionType(str, Enum):
    """Types of actions that can be tracked"""
    WS_MESSAGE_SENT = "ws_message_sent"
    EMAIL_SENT = "email_sent"
    NOTIFICATION_SENT = "notification_sent"
    # Add more action types as needed
    
class ActionRecord(BaseModel):
    """Record of a single action taken"""
    action_type: ActionType
    timestamp: datetime
    success: bool
    metadata: Optional[dict] = None  # Store phone, message_id, etc.
    error: Optional[str] = None