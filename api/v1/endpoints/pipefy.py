import logging
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, status
from core.config import settings
from repositories.pipefy_data import PipeFyDataRepository
from repositories.card_actions import CardActionsRepository
from repositories.pipefy_events import PipefyEventsRepository
from schemas.pipefy_events import SyncCardsRequest, SyncCardsResponse
from services.pipefy_service import process_card_details

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/sync-cards",
    response_model=SyncCardsResponse,
    summary="Sync all cards from a Pipefy phase",
    tags=["pipefy"]
)
async def sync_phase_cards(request: SyncCardsRequest):
    """
    Fetch cards from a Pipefy phase with pagination support.

    This endpoint:
    1. Fetches cards from the specified phase using Pipefy GraphQL API (with pagination)
    2. For each card, fetches nested cards (user_data, user_car_information)
    3. Queries existing actions from card_actions table
    4. Saves each card as an event in pipefy_events table with webhook-compatible format

    **Pagination:**
    - First request: Send without `cursor` to get the first page
    - Subsequent requests: Use the `next_cursor` from the previous response
    - Continue until `has_more_pages` is `false`

    **Request Body:**
    - `phase_id`: Pipefy phase ID to sync cards from
    - `organization_id`: UUID of the organization
    - `cursor`: (Optional) Pagination cursor from previous response
    - `limit`: (Optional) Number of cards per page (default: 50, max: 50)

    **Response:**
    - `success`: Whether the sync was successful
    - `phase_id`: The phase ID that was synced
    - `phase_name`: The name of the phase
    - `total_cards_in_phase`: Total number of cards in the phase
    - `total_cards_fetched`: Number of cards fetched in this request
    - `total_events_created`: Number of events created in database
    - `cards_synced`: List of card IDs that were synced
    - `has_more_pages`: Whether there are more cards to fetch
    - `next_cursor`: Cursor to use for the next page

    **Example Usage:**
    ```javascript
    // Frontend pagination example
    let cursor = null;
    let allCards = [];

    do {
      const response = await fetch('/api/pipefy/sync-cards', {
        method: 'POST',
        body: JSON.stringify({
          phase_id: "341972150",
          organization_id: "org-uuid",
          cursor: cursor,
          limit: 50
        })
      });

      const data = await response.json();
      allCards.push(...data.cards_synced);
      cursor = data.next_cursor;

    } while (data.has_more_pages);
    ```
    """
    try:
        # Initialize repository
        pipefy_repo = PipeFyDataRepository(settings.PIPEFY_API_TOKEN)

        # Step 1: Fetch cards from Pipefy with pagination
        logger.info(f"Fetching cards from phase {request.phase_id} (cursor: {request.cursor}, limit: {request.limit})")

        cards_result = await pipefy_repo.get_all_cards_in_phase(
            phase_id=request.phase_id,
            first=request.limit,
            after=request.cursor
        )

        cards = cards_result.get("cards", [])
        page_info = cards_result.get("pageInfo", {})
        phase_name = cards_result.get("phase_name")
        cards_count = cards_result.get("cards_count")

        # Step 2: Query existing cards from card_actions table
        card_actions_repo = CardActionsRepository()
        existing_card_ids = await card_actions_repo.get_all_card_ids()

        # Filter out cards that already exist in card_actions
        original_count = len(cards)
        cards = [card for card in cards if card["id"] not in existing_card_ids]
        filtered_count = original_count - len(cards)

        if filtered_count > 0:
            logger.info(f"Filtered out {filtered_count} cards that already exist in card_actions")
        logger.info(f"Processing {len(cards)} new cards (out of {original_count} total)")

        if not cards:
            logger.info(f"No cards found in phase {request.phase_id}")
            return SyncCardsResponse(
                success=True,
                phase_id=request.phase_id,
                phase_name=phase_name,
                organization_id=request.organization_id,
                total_cards_in_phase=cards_count,
                total_cards_fetched=0,
                total_events_created=0,
                cards_synced=[],
                has_more_pages=False,
                next_cursor=None
            )

        logger.info(f"Fetched {len(cards)} cards from Pipefy")

        # Step 2: Process each card using the same method as webhook
        card_ids: List[str] = []
        processed_count = 0

        logger.info(f"Processing {len(cards)} cards using process_card_details method")

        for card in cards:
            card_id = card["id"]
            card_ids.append(card_id)

            try:
                # Use the exact same method as webhook to process and save the card
                result = await process_card_details(card_id)
                processed_count += 1
                logger.info(f"Processed card {card_id} ({processed_count}/{len(cards)})")
            except Exception as e:
                logger.error(f"Error processing card {card_id}: {str(e)}", exc_info=True)
                # Continue processing other cards even if one fails

        logger.info(f"Successfully processed {processed_count} out of {len(cards)} cards")

        # Build response
        return SyncCardsResponse(
            success=True,
            phase_id=request.phase_id,
            phase_name=phase_name,
            organization_id=request.organization_id,
            total_cards_in_phase=cards_count,
            total_cards_fetched=len(cards),
            total_events_created=processed_count,
            cards_synced=card_ids,
            has_more_pages=page_info.get("hasNextPage", False),
            next_cursor=page_info.get("endCursor")
        )

    except Exception as e:
        logger.error(f"Error syncing cards from phase {request.phase_id}: {str(e)}", exc_info=True)

        # Return error response
        return SyncCardsResponse(
            success=False,
            phase_id=request.phase_id,
            phase_name=None,
            organization_id=request.organization_id,
            total_cards_in_phase=None,
            total_cards_fetched=0,
            total_events_created=0,
            cards_synced=[],
            has_more_pages=False,
            next_cursor=None,
            error=str(e)
        )
