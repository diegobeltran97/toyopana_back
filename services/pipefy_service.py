from schemas.pipefy_events import PipefyEventUpdateActions, PipefyEventResponse
from repositories.pipefy_data import PipeFyDataRepository
from repositories.pipefy_events import PipefyEventsRepository
from schemas.webhook import (
    PipefyWebhookData,
    PhaseRef,
    MovedBy,
    CardRef,
    CardData,
    NestedCardData,
    PhaseData,
    FieldData
)
from core.config import settings
from typing import Dict, Any


async def update_event_actions(
    event_id: str,
    actions_taken: Dict[str, Any]
) -> PipefyEventResponse:
    """
    Update the actions taken for a specific event by event ID

    Args:
        event_id: The UUID of the event to update
        actions_taken: Dictionary of actions taken (e.g., whatsapp_sent, message_id, etc.)

    Returns:
        Updated event record

    Example:
        await update_event_actions(
            event_id="550e8400-e29b-41d4-a716-446655440000",
            actions_taken={
                "whatsapp_sent": True,
                "message_id": "msg_abc123",
                "sent_at": "2024-01-15T10:30:00Z"
            }
        )
    """
    repo = PipefyEventsRepository()

    # Create update schema
    update_data = PipefyEventUpdateActions(actions_taken=actions_taken)

    # Update the event
    updated_event = await repo.update_event_actions_by_id(event_id, update_data)

    return updated_event


async def update_event_actions_by_card_id(
    pipefy_card_id: str,
    actions_taken: Dict[str, Any]
) -> PipefyEventResponse:
    """
    Find the most recent event for a card and update its actions

    Args:
        pipefy_card_id: The Pipefy card ID
        actions_taken: Dictionary of actions taken

    Returns:
        Updated event record

    Raises:
        HTTPException: If no event found for the card

    Example:
        await update_event_actions_by_card_id(
            pipefy_card_id="123456",
            actions_taken={
                "whatsapp_sent": True,
                "message_id": "msg_abc123",
                "sent_at": datetime.utcnow().isoformat()
            }
        )
    """
    repo = PipefyEventsRepository()

    # Get the most recent event for this card (limit=1 returns the latest)
    events = await repo.get_events_by_card(pipefy_card_id=pipefy_card_id, limit=1)

    if not events or len(events) == 0:
        raise Exception(f"No event found for card {pipefy_card_id}")

    # Get the event ID from the most recent event
    event_id = events[0].get("id")

    # Update the actions
    return await update_event_actions(event_id, actions_taken)

async def process_card_details(card_id: str):
     # Placeholder for processing card details

    # Initialize repository
    pipefy_repo = PipeFyDataRepository(settings.PIPEFY_API_TOKEN)

    # Get card details
    card_data = await pipefy_repo.get_card_details(card_id)
    
    print(f"Fetched card details for card ID {card_id}: {card_data}")  # Debugging output

    #First we'll get the card that array values is different from null,
    field_maping = card_data.get("fields", [])
    field_to_value = {field["field"]["id"]: field["array_value"][0] for field in field_maping if field.get("array_value") is not None}

    print("Field to Value Mapping:", field_to_value)  # Debugging output

    # Fetch nested cards with error handling
    user_data = None
    user_car_information = None

    if "nombre" in field_to_value:
        try:
            user_data = await pipefy_repo.get_card_details(str(field_to_value.get("nombre")))
            print(f"Fetched user_data: {user_data}")  # Debugging output
        except Exception as e:
            print(f"Warning: Could not fetch user_data card: {str(e)}")

    if "auto_a_recibit" in field_to_value:
        try:
            user_car_information = await pipefy_repo.get_card_details(str(field_to_value.get("auto_a_recibit")))
        except Exception as e:
            print(f"Warning: Could not fetch user_car_information card: {str(e)}")
    
    
    # Create CardData instance with proper typing
    card_to_save: CardData = CardData(
        id=card_data.get("id"),
        title=card_data.get("title"),
        current_phase=card_data.get("current_phase"),
        pipe=card_data.get("pipe", {}).get("name") if card_data.get("pipe") else None,
        fields=card_data.get("fields", []),
        user_data=user_data,
        user_car_information=user_car_information,
        assignees=card_data.get("assignees"),
        labels=card_data.get("labels"),
        created_at=card_data.get("created_at"),
        updated_at=card_data.get("updated_at"),
        due_date=card_data.get("due_date"),
        url=card_data.get("url")
    )


    db_repo = PipefyEventsRepository()

    #save card details to database or perform any necessary processing here
    # For example, you could save the card details to a database or trigger other actions based on the card data
    data = await db_repo.create_event(
        organization_id=str(settings.ORGANIZATION_ID),
        event_type="card_details_fetched",
        raw_payload=card_to_save.model_dump(),
        pipefy_card_id=card_id,

    )

    return {"card_id": card_id, "details": card_to_save.model_dump(), "event": data}