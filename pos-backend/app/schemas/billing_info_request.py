"""Pydantic schema for the 'request billing info' action's response."""

from pydantic import BaseModel


class BillingInfoRequestResponse(BaseModel):
    """Confirms a billing-info-request email was sent and where the address came from."""

    sent_to: str
    source_level: str
