"""Domain payloads for the send-ws-message use-case."""

from pydantic import BaseModel, ConfigDict, Field


class OrderPayload(BaseModel):
    """The full order object the client sends alongside a message.

    Only ``id`` is required (it drives the status advance). ``extra="allow"``
    keeps every other order field the client sends, so future anti-spam or
    post-send logic can read any of them without a contract change.
    """

    model_config = ConfigDict(extra="allow")

    id: str = Field(..., description="The order id to advance after sending")
