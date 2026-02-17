from repositories.pipefy_data import PipeFyDataRepository
from repositories.pipefy_events import PipefyEventsRepository
from core.config import settings

async def process_card_details(card_id: str):
    # Placeholder for processing card details
    
    
    # Initialize repository
    pipefy_repo = PipeFyDataRepository(settings.PIPEFY_API_TOKEN)

    # Get card details
    card_data = await pipefy_repo.get_card_details(card_id)
    
    
    db_repo = PipefyEventsRepository()

    #save card details to database or perform any necessary processing here
    # For example, you could save the card details to a database or trigger other actions based on the card data
    data = await db_repo.create_event(
        organization_id=str(settings.ORGANIZATION_ID),
        event_type="card_details_fetched",
        raw_payload=card_data,
        pipefy_card_id=card_id,
        
    )
    
    return {"card_id": card_id, "details": card_data, "event": data}