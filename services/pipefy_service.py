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

async def process_card_details(card_id: str):
    # Placeholder for processing card details
    
    
    # Initialize repository
    pipefy_repo = PipeFyDataRepository(settings.PIPEFY_API_TOKEN)

    # Get card details
    card_data = await pipefy_repo.get_card_details(card_id)
    
    #First we'll get the card that array values is different from null,
    field_maping = card_data.get("fields", [])
    field_to_value = {field["field"]["id"]: field["array_value"][0] for field in field_maping if field.get("array_value") is not None}
    
    print("Field to Value Mapping:", field_to_value)  # Debugging output
    user_data = await pipefy_repo.get_card_details(str(field_to_value.get("cliente_a_recibir")))
    user_car_information = await pipefy_repo.get_card_details(str(field_to_value.get("auto_a_recibit")))
    
    
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