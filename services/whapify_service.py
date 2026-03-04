import httpx
import logging
from core.config import settings
from services.pipefy_service import  update_event_actions

logger = logging.getLogger(__name__)


def format_phone_number(phone: str) -> str:
    """
    Format phone number to WhatsApp format: {country_code}{number}@s.whatsapp.net

    Example:
        Input: "5215512345678" or "+52 55 1234 5678"
        Output: "5215512345678@s.whatsapp.net"
    """
    # Remove any non-digit characters
    clean_phone = ''.join(filter(str.isdigit, phone))

    # Ensure it starts with country code (Panama = 507)
    if not clean_phone.startswith('507'):
        clean_phone = '50' + clean_phone

    return f"{clean_phone}@s.whatsapp.net"


async def send_whatsapp_message(phone: str, message: str) -> dict:
    """
    Send a WhatsApp text message via Whapify API.

    Args:
        phone: Customer phone number (will be formatted to WhatsApp format)
        message: Text message to send

    Returns:
        dict: Response from Whapify API

    Raises:
        Does not raise exceptions - logs errors and returns error dict instead.
        This ensures background task failures don't break the webhook flow.
    """
    try:
        # Format phone number to WhatsApp format
        whatsapp_phone = format_phone_number(phone)

        logger.info(f"Sending WhatsApp message to {whatsapp_phone}")

        # Prepare request
        url = f"{settings.WHAPIFY_BASE_URL}/messages/text"
        headers = {
            "Authorization": f"Bearer {settings.WHAPIFY_API_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {
            "to": whatsapp_phone,
            "body": message,
        }

        # Send message
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=headers, json=payload)

        # Handle response
        if response.status_code == 200:
            logger.info(f"WhatsApp message sent successfully to {whatsapp_phone}")
            
            return {"success": True, "data": response.json()}

        elif response.status_code == 401:
            logger.error("Whapify authentication failed - check WHAPIFY_API_TOKEN in .env")
            return {"success": False, "error": "auth_failed", "status_code": 401}

        elif response.status_code == 429:
            logger.warning(f"Whapify rate limit hit for {whatsapp_phone}")
            return {"success": False, "error": "rate_limit", "status_code": 429}

        else:
            logger.error(f"Whapify API error: {response.status_code} - {response.text}")
            return {"success": False, "error": "api_error", "status_code": response.status_code}

    except httpx.TimeoutException:
        logger.error(f"Whapify API timeout when sending message to {phone}")
        return {"success": False, "error": "timeout"}

    except Exception as e:
        logger.error(f"Unexpected error sending WhatsApp message: {str(e)}")
        return {"success": False, "error": "unexpected", "details": str(e)}


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
    message = f"Hola {customer_name}, tu {car_info} tiene cita para el día de mañana"

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
        

    


 