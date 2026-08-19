"""Whapi connection settings.

Each provider validates its own credential shape, because the vendors need
genuinely different fields (Whapi a token + base URL; Meta an access token,
phone_number_id, waba_id and app_secret; Twilio an account_sid, auth_token and
from-number). Keeping the shape with the adapter means adding a provider never
touches a shared model.

The values are passed in, never read from settings here -- that is what lets
the same adapter run on env-backed config today and per-organization config
from a table later.
"""

from pydantic import BaseModel, Field


class WhapiCredentials(BaseModel):
    """Everything WhapiClient needs to talk to a Whapi.cloud account."""

    token: str = Field(..., min_length=1, description="Whapi API bearer token")
    base_url: str = Field(
        "https://gate.whapi.cloud", description="Whapi REST API base URL"
    )
