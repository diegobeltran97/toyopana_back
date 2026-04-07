from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from services.whapify_service import (
    send_delivery_notification,
    get_labels_with_associations,
    get_labels_stats,
)
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


@router.get(
    "/whatsapp/labels",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Get WhatsApp Labels with Associations",
    tags=["whatsapp"]
)
async def get_whatsapp_labels(filter_today: bool = False):
    """
    Retrieve all WhatsApp labels with their associated chats and messages.

    Args:
        filter_today: Optional query parameter. If True, only include chats from today.
                     Example: /api/whatsapp/labels?filter_today=true

    Returns:
        List of labels, each enriched with:
        - id: Label identifier
        - name: Label display name
        - color: Label color
        - count: Number of items with this label
        - chats: Array of chat objects associated with this label (filtered by today if requested)
        - messages: Array of message objects associated with this label

    Example response:
    ```json
    {
        "success": true,
        "data": [
            {
                "id": "10",
                "name": "Cita de Taller",
                "color": "deepskyblue",
                "count": 3,
                "chats": [
                    {
                        "id": "5075512345678@s.whatsapp.net",
                        "name": "Juan Pérez"
                    }
                ],
                "messages": []
            }
        ]
    }
    ```
    """
    try:
        logger.info(
            f"Fetching WhatsApp labels with associations "
            f"(filter_today={filter_today})"
        )

        # Call the whapify service
        result = await get_labels_with_associations(filter_today_chats=filter_today)

        if result.get("success"):
            labels = result.get("data", [])
            logger.info(f"Successfully retrieved {len(labels)} labels with associations")

            return {
                "success": True,
                "data": labels,
                "count": len(labels)
            }
        else:
            # Service failed
            error_type = result.get("error")
            error_details = result.get("details", "")

            logger.error(f"Failed to fetch labels: {error_type} - {error_details}")

            # Return error response based on error type
            error_messages = {
                "auth_failed": "WhatsApp API authentication failed. Please check configuration.",
                "rate_limit": "WhatsApp API rate limit exceeded. Please try again later.",
                "timeout": "WhatsApp API request timed out. Please try again.",
                "unexpected": f"Unexpected error: {error_details}"
            }

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_messages.get(error_type, "Failed to fetch WhatsApp labels")
            )

    except HTTPException:
        # Re-raise HTTPExceptions
        raise
    except Exception as e:
        logger.error(f"Error in get_whatsapp_labels endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching WhatsApp labels: {str(e)}"
        )


@router.get(
    "/whatsapp/statsLabels",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Get WhatsApp Label Statistics",
    tags=["whatsapp"]
)
async def get_whatsapp_label_stats(filter_today: bool = False):
    """
    Retrieve statistics for all WhatsApp labels (count of chats and messages per label).

    This endpoint returns the same labels as `/whatsapp/labels` but only includes
    the count of chats and messages instead of the full arrays, making it more
    lightweight for dashboard statistics.

    Args:
        filter_today: Optional query parameter. If True, only count chats from today.
                     Example: /api/whatsapp/statsLabels?filter_today=true

    Returns:
        List of labels with statistics:
        - id: Label identifier
        - name: Label display name
        - color: Label color
        - count: Original count from API (may be null)
        - chats: Number of chats associated with this label
        - messages: Number of messages associated with this label

    Example response:
    ```json
    {
        "success": true,
        "data": [
            {
                "id": "10",
                "name": "Cita de Taller",
                "color": "deepskyblue",
                "count": null,
                "chats": 23,
                "messages": 5
            },
            {
                "id": "39",
                "name": "Llamo",
                "color": "mediumaquamarine",
                "count": null,
                "chats": 15,
                "messages": 2
            }
        ],
        "count": 2
    }
    ```
    """
    try:
        logger.info(
            f"Fetching WhatsApp label statistics "
            f"(filter_today={filter_today})"
        )

        # Call the whapify service
        result = await get_labels_stats(filter_today_chats=filter_today)

        if result.get("success"):
            stats = result.get("data", [])
            logger.info(f"Successfully calculated statistics for {len(stats)} labels")

            # Calculate total chats and messages across all labels
            total_chats = sum(label.get("chats", 0) for label in stats)
            total_messages = sum(label.get("messages", 0) for label in stats)

            return {
                "success": True,
                "data": stats,
                "count": len(stats),
                "totals": {
                    "chats": total_chats,
                    "messages": total_messages
                }
            }
        else:
            # Service failed
            error_type = result.get("error")
            error_details = result.get("details", "")

            logger.error(f"Failed to fetch label statistics: {error_type} - {error_details}")

            # Return error response based on error type
            error_messages = {
                "auth_failed": "WhatsApp API authentication failed. Please check configuration.",
                "rate_limit": "WhatsApp API rate limit exceeded. Please try again later.",
                "timeout": "WhatsApp API request timed out. Please try again.",
                "unexpected": f"Unexpected error: {error_details}"
            }

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_messages.get(error_type, "Failed to fetch WhatsApp label statistics")
            )

    except HTTPException:
        # Re-raise HTTPExceptions
        raise
    except Exception as e:
        logger.error(f"Error in get_whatsapp_label_stats endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching WhatsApp label statistics: {str(e)}"
        )
