from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from services.whapify_service import send_delivery_notification
from typing import Dict, Any
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


class SendWhatsAppRequest(BaseModel):
    """Request model for sending WhatsApp messages"""
    card_id: str
    customer_name: str
    car_info: str
    phone: str


@router.post(
    "/whatsapp/send-notification",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Send WhatsApp Delivery Notification",
    tags=["whatsapp"]
)
async def send_whatsapp_notification(request: SendWhatsAppRequest):
    """
    Send a hardcoded WhatsApp delivery notification to a customer.

    This endpoint is triggered from the frontend when a user clicks
    the "Send WhatsApp" button in the customer table.

    Args:
        request: Contains customer_name, car_info, and phone number

    Returns:
        Success status and Whapify API response

    Example request:
    ```json
    {
        "card_id": "123456",
        "customer_name": "Diego",
        "car_info": "Toyota Camry 2020",
        "phone": "5512345678"
    }
    ```
    """
    try:
        logger.info(f"Sending WhatsApp notification to {request.customer_name}")
        
        # Call the whapify service
        result = await send_delivery_notification(
            card_id=request.card_id,
            customer_name=request.customer_name,
            car_info=request.car_info,
            phone=request.phone
        )

        # Check if the message was sent successfully
        if result.get("success"):
            logger.info(f"WhatsApp message sent successfully to {request.customer_name}")
            
            return {
                "success": True,
                "message": f"WhatsApp notification sent to {request.customer_name}",
                "data": result.get("data")
            }
        else:
            # WhatsApp API failed, but we don't raise an exception
            # Return the error info to the frontend
            error_type = result.get("error")
            status_code = result.get("status_code", 500)

            logger.error(f"WhatsApp API error: {error_type}")

            # Return appropriate error message based on error type
            error_messages = {
                "auth_failed": "WhatsApp API authentication failed. Please check configuration.",
                "rate_limit": "WhatsApp API rate limit exceeded. Please try again later.",
                "timeout": "WhatsApp API request timed out. Please try again.",
                "api_error": f"WhatsApp API error (status {status_code})",
                "unexpected": f"Unexpected error: {result.get('details')}"
            }

            return {
                "success": False,
                "message": error_messages.get(error_type, "Failed to send WhatsApp message"),
                "error": error_type,
                "status_code": status_code
            }

    except Exception as e:
        logger.error(f"Error in send_whatsapp_notification endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error sending WhatsApp notification: {str(e)}"
        )
