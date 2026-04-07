import logging
from typing import List, Dict, Any
from core.config import settings
from services.pipefy_service import update_event_actions
from repositories.whapify_repository import WhapifyRepository

logger = logging.getLogger(__name__)

# Initialize repository singleton
_whapify_repo: WhapifyRepository | None = None


def get_whapify_repository() -> WhapifyRepository:
    """
    Get or create singleton instance of WhapifyRepository.

    Returns:
        WhapifyRepository instance configured with settings
    """
    global _whapify_repo
    if _whapify_repo is None:
        _whapify_repo = WhapifyRepository(
            api_token=settings.WHAPIFY_API_TOKEN,
            base_url=settings.WHAPIFY_BASE_URL,
        )
    return _whapify_repo


def format_phone_number(phone: str) -> str:
    """
    Format phone number to WhatsApp format: {country_code}{number}@s.whatsapp.net

    Example:
        Input: "5215512345678" or "+52 55 1234 5678"
        Output: "5215512345678@s.whatsapp.net"

    Note:
        This is a convenience wrapper around WhapifyRepository.format_phone_number
        for backward compatibility.
    """
    return WhapifyRepository.format_phone_number(phone, country_code="507")


async def send_whatsapp_message(phone: str, message: str) -> dict:
    """
    Send a WhatsApp text message via Whapify API.

    Args:
        phone: Customer phone number (will be formatted to WhatsApp format)
        message: Text message to send

    Returns:
        dict: Response from Whapify API with keys:
            - success (bool): Whether the operation succeeded
            - data (dict, optional): Response data if successful
            - error (str, optional): Error type if failed
            - status_code (int, optional): HTTP status code if applicable

    Raises:
        Does not raise exceptions - logs errors and returns error dict instead.
        This ensures background task failures don't break the webhook flow.
    """
    repo = get_whapify_repository()

    # Format phone number to WhatsApp format
    whatsapp_phone = format_phone_number(phone)

    logger.info(f"Sending WhatsApp message to {whatsapp_phone}")

    # Use repository to send message
    result = await repo.send_text_message(
        to=whatsapp_phone,
        body=message,
    )

    return result


async def get_labels_with_associations(filter_today_chats: bool = False) -> Dict[str, Any]:
    """
    Fetch all WhatsApp labels and enrich each with its associated chats and messages.

    Args:
        filter_today_chats: If True, only include chats from today in the associations.
                           Useful for filtering recent conversations. Defaults to False.

    Returns:
        dict: Response with keys:
            - success (bool): Whether the operation succeeded
            - data (List[EnrichedLabel]): List of labels with their associations
            - error (str, optional): Error type if failed

    Example response:
        {
            "success": True,
            "data": [
                {
                    "id": "10",
                    "name": "Cita de Taller",
                    "color": "deepskyblue",
                    "count": 3,
                    "chats": [
                        {"id": "5075512345678@s.whatsapp.net", "name": "Juan Pérez"}
                    ],
                    "messages": []
                }
            ]
        }
    """
    repo = get_whapify_repository()

    try:
        # Step 1: Fetch all labels
        logger.info("Fetching all WhatsApp labels")
        labels_result = await repo.get_labels()

        if not labels_result.get("success"):
            logger.error(f"Failed to fetch labels: {labels_result.get('error')}")
            return labels_result

        # The API returns labels directly as a list in 'data', not nested under 'labels'
        labels_data = labels_result.get("data", [])

        # Handle both formats: list or dict with 'labels' key
        if isinstance(labels_data, dict):
            labels = labels_data.get("labels", [])
        else:
            labels = labels_data

        logger.info(f"Found {len(labels)} labels")

        # Step 2: Fetch associations for each label
        enriched_labels: List[Dict[str, Any]] = []

        for label in labels:
            label_id = label.get("id")
            logger.info(f"Fetching associations for label: {label.get('name')} (ID: {label_id})")

            # Get associations for this label
            associations_result = await repo.get_label_associations(
                label_id,
                filter_today_chats=filter_today_chats
            )

            if associations_result.get("success"):
                associations_data = associations_result.get("data", {})
                chats = associations_data.get("chats", [])
                messages = associations_data.get("messages", [])

                # Build enriched label object
                enriched_label = {
                    "id": label.get("id"),
                    "name": label.get("name"),
                    "color": label.get("color"),
                    "count": label.get("count"),
                    "chats": chats,
                    "messages": messages,
                }

                enriched_labels.append(enriched_label)
                logger.info(
                    f"Label '{label.get('name')}': {len(chats)} chats, {len(messages)} messages"
                )
            else:
                # If we can't fetch associations, include label without associations
                logger.warning(
                    f"Failed to fetch associations for label {label_id}: {associations_result.get('error')}"
                )
                enriched_label = {
                    "id": label.get("id"),
                    "name": label.get("name"),
                    "color": label.get("color"),
                    "count": label.get("count"),
                    "chats": [],
                    "messages": [],
                }
                enriched_labels.append(enriched_label)

        logger.info(f"Successfully enriched {len(enriched_labels)} labels with associations")

        return {
            "success": True,
            "data": enriched_labels,
        }

    except Exception as e:
        logger.error(f"Unexpected error fetching labels with associations: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": "unexpected",
            "details": str(e),
        }


async def get_labels_stats(filter_today_chats: bool = False) -> Dict[str, Any]:
    """
    Fetch WhatsApp labels and return statistics (count of chats and messages per label).

    Args:
        filter_today_chats: If True, only count chats from today in the statistics.
                           Defaults to False.

    Returns:
        dict: Response with keys:
            - success (bool): Whether the operation succeeded
            - data (List[LabelStats]): List of labels with chat/message counts
            - error (str, optional): Error type if failed

    Example response:
        {
            "success": True,
            "data": [
                {
                    "id": "10",
                    "name": "Cita de Taller",
                    "color": "deepskyblue",
                    "count": None,
                    "chats": 23,
                    "messages": 5
                }
            ]
        }
    """
    # Reuse the existing get_labels_with_associations method
    result = await get_labels_with_associations(filter_today_chats=filter_today_chats)

    if not result.get("success"):
        return result

    # Transform enriched labels to stats format
    enriched_labels = result.get("data", [])
    stats_labels = []

    for label in enriched_labels:
        stats_label = {
            "id": label.get("id"),
            "name": label.get("name"),
            "color": label.get("color"),
            "count": label.get("count"),
            "chats": len(label.get("chats", [])),  # Count of chats
            "messages": len(label.get("messages", [])),  # Count of messages
        }
        stats_labels.append(stats_label)

    logger.info(f"Calculated statistics for {len(stats_labels)} labels")

    return {
        "success": True,
        "data": stats_labels,
    }


async def send_delivery_notification(card_id: str, customer_name: str, car_info: str, phone: str) -> dict:
    """
    Send a hardcoded delivery notification template via WhatsApp.

    Args:
        card_id: The Pipefy card ID
        customer_name: Customer's name
        car_info: Car details (e.g., "Toyota Camry 2020")
        phone: Customer's phone number

    Returns:
        dict: Response from send_whatsapp_message
    """
    # Hardcoded template in Spanish
    message = f"Estimado {customer_name}, hace unos dias realizamos un diagnotico del vehiculo {car_info} queremos saber si tiene alguna duda de la cotizacion o si desea agendar una cita para el servicio. ¡Gracias por confiar en Toyopana!"

    logger.info(f"Preparing delivery notification for {customer_name} - {car_info}")
    
    try:
        result = await send_whatsapp_message(phone=phone, message=message)
        
        await update_event_actions(event_id=card_id, actions_taken={"whatsapp_sent": True})
        
        
        if result.get("success"):
            logger.info(f"Delivery notification sent successfully to {customer_name}")
            
            return result
        else:
            logger.error(f"Failed to send delivery notification to {customer_name}: {result.get('error')}")
    except Exception as e:
        logger.error(f"Error sending delivery notification: {str(e)}", exc_info=True)
        return {"success": False, "error": "unexpected", "details": str(e)}
        

    


 