# app/repositories/whapify_repository.py
"""Repository for interacting with Whapi.cloud WhatsApp API"""

import httpx
import logging
from typing import Optional, Dict, Any, List, Union
from datetime import datetime, timezone
from schemas.whapi import (
    SendTextMessageRequest,
    SendMessageResponse,
    Label,
    LabelsResponse,
    CreateLabelRequest,
    LabelAssociations,
    WhapifySuccessResponse,
    WhapifyErrorResponse,
    LabelColor,
)

logger = logging.getLogger(__name__)


class WhapifyRepository:
    """
    Repository for interacting with Whapi.cloud WhatsApp Business API.

    Provides methods for:
    - Sending text messages
    - Managing labels (create, get, delete)
    - Managing label associations with chats and messages

    Reference: https://whapi.readme.io/reference/
    """

    BASE_URL = "https://gate.whapi.cloud"

    def __init__(self, api_token: str, base_url: Optional[str] = None):
        """
        Initialize Whapify repository with API token.

        Args:
            api_token: Whapi.cloud API Bearer token
            base_url: Optional custom base URL (defaults to https://gate.whapi.cloud)
        """
        self.api_token = api_token
        self.base_url = base_url or self.BASE_URL
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

    async def _handle_response(
        self,
        response: httpx.Response,
        success_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handle HTTP response and return standardized result dictionary.

        Args:
            response: httpx Response object
            success_message: Optional custom success message

        Returns:
            Dictionary with success status and data or error info
        """
        if response.status_code == 200 or response.status_code == 201:
            logger.info(success_message or f"Request successful: {response.status_code}")
            return {"success": True, "data": response.json()}

        elif response.status_code == 400:
            logger.error(f"Bad request: {response.text}")
            return {"success": False, "error": "bad_request", "status_code": 400, "details": response.text}

        elif response.status_code == 401:
            logger.error("Authentication failed - check WHAPIFY_API_TOKEN")
            return {"success": False, "error": "auth_failed", "status_code": 401}

        elif response.status_code == 402:
            logger.warning("Trial version limit exceeded")
            return {"success": False, "error": "trial_limit_exceeded", "status_code": 402}

        elif response.status_code == 403:
            logger.error("Forbidden - cannot send to this recipient or perform this action")
            return {"success": False, "error": "forbidden", "status_code": 403}

        elif response.status_code == 413:
            logger.error("Request body too large")
            return {"success": False, "error": "payload_too_large", "status_code": 413}

        elif response.status_code == 429:
            logger.warning("Rate limit exceeded")
            return {"success": False, "error": "rate_limit", "status_code": 429}

        elif response.status_code == 500:
            logger.error(f"Whapi server error: {response.text}")
            return {"success": False, "error": "server_error", "status_code": 500}

        else:
            logger.error(f"Unexpected status code {response.status_code}: {response.text}")
            return {"success": False, "error": "unexpected_error", "status_code": response.status_code}

    # ========================================================================
    # MESSAGE METHODS
    # ========================================================================

    async def send_text_message(
        self,
        to: str,
        body: str,
        typing_time: Optional[int] = None,
        no_link_preview: Optional[bool] = None,
        mentions: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Send a text message via WhatsApp.

        Args:
            to: Phone number or Chat ID (format: {country_code}{number}@s.whatsapp.net)
            body: Message text content
            typing_time: Optional simulated typing duration in seconds (0-60)
            no_link_preview: Optional flag to disable link previews
            mentions: Optional array of contact IDs to mention

        Returns:
            Dictionary with success status and message data or error info

        Example:
            >>> result = await repo.send_text_message(
            ...     to="5215512345678@s.whatsapp.net",
            ...     body="Hello! This is a test.",
            ...     typing_time=2
            ... )
            >>> if result["success"]:
            ...     print(f"Message sent: {result['data']['message']['id']}")
        """
        try:
            url = f"{self.base_url}/messages/text"

            # Build request using Pydantic model for validation
            request_data = SendTextMessageRequest(
                to=to,
                body=body,
                typing_time=typing_time,
                no_link_preview=no_link_preview,
                mentions=mentions,
            )

            logger.info(f"Sending text message to {to}")

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers=self.headers,
                    json=request_data.model_dump(exclude_none=True),
                )

            return await self._handle_response(
                response,
                success_message=f"Text message sent successfully to {to}"
            )

        except httpx.TimeoutException:
            logger.error(f"Timeout sending message to {to}")
            return {"success": False, "error": "timeout"}

        except Exception as e:
            logger.error(f"Unexpected error sending message: {str(e)}", exc_info=True)
            return {"success": False, "error": "unexpected", "details": str(e)}

    # ========================================================================
    # LABEL METHODS
    # ========================================================================

    async def get_labels(self) -> Dict[str, Any]:
        """
        Retrieve all registered labels in WhatsApp Business.

        Returns:
            Dictionary with success status and labels array or error info

        Example:
            >>> result = await repo.get_labels()
            >>> if result["success"]:
            ...     for label in result["data"]["labels"]:
            ...         print(f"{label['name']} ({label['color']}): {label['count']} items")
        """
        try:
            url = f"{self.base_url}/labels"

            logger.info("Fetching all WhatsApp labels")

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self.headers)

            return await self._handle_response(
                response,
                success_message="Labels retrieved successfully"
            )

        except httpx.TimeoutException:
            logger.error("Timeout fetching labels")
            return {"success": False, "error": "timeout"}

        except Exception as e:
            logger.error(f"Unexpected error fetching labels: {str(e)}", exc_info=True)
            return {"success": False, "error": "unexpected", "details": str(e)}

    async def create_label(
        self,
        label_id: str,
        name: str,
        color: LabelColor,
    ) -> Dict[str, Any]:
        """
        Create a new WhatsApp label.

        Args:
            label_id: Unique identifier for the label
            name: Display name for the label
            color: Label color (one of 20 predefined colors)

        Returns:
            Dictionary with success status or error info

        Example:
            >>> result = await repo.create_label(
            ...     label_id="urgent",
            ...     name="Urgent",
            ...     color="red"
            ... )
            >>> if result["success"]:
            ...     print("Label created successfully")
        """
        try:
            url = f"{self.base_url}/labels"

            # Build request using Pydantic model for validation
            request_data = CreateLabelRequest(
                id=label_id,
                name=name,
                color=color,
            )

            logger.info(f"Creating label: {name} ({color})")

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers=self.headers,
                    json=request_data.model_dump(),
                )

            return await self._handle_response(
                response,
                success_message=f"Label '{name}' created successfully"
            )

        except httpx.TimeoutException:
            logger.error(f"Timeout creating label {name}")
            return {"success": False, "error": "timeout"}

        except Exception as e:
            logger.error(f"Unexpected error creating label: {str(e)}", exc_info=True)
            return {"success": False, "error": "unexpected", "details": str(e)}

    async def get_label_associations(
        self,
        label_id: str,
        filter_today_chats: bool = False
    ) -> Dict[str, Any]:
        """
        Retrieve objects (chats and messages) associated with a specific label.

        Args:
            label_id: ID of the label to query
            filter_today_chats: If True, only return chats from today (based on chat timestamp)

        Returns:
            Dictionary with success status and associations data or error info

        Example:
            >>> result = await repo.get_label_associations("urgent")
            >>> if result["success"]:
            ...     chats = result["data"]["chats"]
            ...     messages = result["data"]["messages"]
            ...     print(f"Label has {len(chats)} chats and {len(messages)} messages")

            >>> # Get only today's chats
            >>> result = await repo.get_label_associations("urgent", filter_today_chats=True)
        """
        try:
            url = f"{self.base_url}/labels/{label_id}"

            logger.info(f"Fetching associations for label: {label_id}")

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self.headers)

            result = await self._handle_response(
                response,
                success_message=f"Label associations retrieved for {label_id}"
            )

            # Apply today filter if requested
            if result.get("success") and filter_today_chats:
                data = result.get("data", {})
                chats = data.get("chats", [])

                # Get today's date at 6 AM in UTC
                today_start = datetime.now(timezone.utc).replace(
                    hour=6, minute=0, second=0, microsecond=0
                )
                today_timestamp = datetime(2026, 3, 1)
                
                print(f"Today's timestamp: {today_timestamp}")

                # Filter chats by timestamp (if available)
                filtered_chats = []
                for chat in chats:
                    # Check if chat has a timestamp field
                    chat_timestamp = chat.get("timestamp") or chat.get("last_message_timestamp")
                    
                    

                    if chat_timestamp:
                        # If timestamp exists, filter by today
                        if datetime.fromtimestamp(chat_timestamp) >= today_timestamp:
                            print(f"Chat timestamp: {chat_timestamp}")
                            filtered_chats.append(chat)
                    else:
                        # If no timestamp, include the chat (safe default)
                        filtered_chats.append(chat)

                original_count = len(chats)
                filtered_count = len(filtered_chats)

                logger.info(
                    f"Filtered chats for label {label_id}: "
                    f"{original_count} total → {filtered_count} today"
                )

                # Update the result with filtered chats
                result["data"]["chats"] = filtered_chats

            return result

        except httpx.TimeoutException:
            logger.error(f"Timeout fetching associations for label {label_id}")
            return {"success": False, "error": "timeout"}

        except Exception as e:
            logger.error(f"Unexpected error fetching label associations: {str(e)}", exc_info=True)
            return {"success": False, "error": "unexpected", "details": str(e)}

    async def add_label_association(
        self,
        label_id: str,
        association_id: str,
    ) -> Dict[str, Any]:
        """
        Assign a label to a chat or message.

        Args:
            label_id: ID of the label to assign
            association_id: Chat ID or Message ID to label

        Returns:
            Dictionary with success status or error info

        Example:
            >>> result = await repo.add_label_association(
            ...     label_id="urgent",
            ...     association_id="5215512345678@s.whatsapp.net"
            ... )
            >>> if result["success"]:
            ...     print("Label assigned successfully")
        """
        try:
            url = f"{self.base_url}/labels/{label_id}/{association_id}"

            logger.info(f"Adding label {label_id} to {association_id}")

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=self.headers)

            return await self._handle_response(
                response,
                success_message=f"Label {label_id} assigned to {association_id}"
            )

        except httpx.TimeoutException:
            logger.error(f"Timeout adding label association")
            return {"success": False, "error": "timeout"}

        except Exception as e:
            logger.error(f"Unexpected error adding label association: {str(e)}", exc_info=True)
            return {"success": False, "error": "unexpected", "details": str(e)}

    async def remove_label_association(
        self,
        label_id: str,
        association_id: str,
    ) -> Dict[str, Any]:
        """
        Remove a label from a chat or message.

        Args:
            label_id: ID of the label to remove
            association_id: Chat ID or Message ID to unlabel

        Returns:
            Dictionary with success status or error info

        Example:
            >>> result = await repo.remove_label_association(
            ...     label_id="urgent",
            ...     association_id="5215512345678@s.whatsapp.net"
            ... )
            >>> if result["success"]:
            ...     print("Label removed successfully")
        """
        try:
            url = f"{self.base_url}/labels/{label_id}/{association_id}"

            logger.info(f"Removing label {label_id} from {association_id}")

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(url, headers=self.headers)

            return await self._handle_response(
                response,
                success_message=f"Label {label_id} removed from {association_id}"
            )

        except httpx.TimeoutException:
            logger.error(f"Timeout removing label association")
            return {"success": False, "error": "timeout"}

        except Exception as e:
            logger.error(f"Unexpected error removing label association: {str(e)}", exc_info=True)
            return {"success": False, "error": "unexpected", "details": str(e)}

    # ========================================================================
    # UTILITY METHODS
    # ========================================================================

    @staticmethod
    def format_phone_number(phone: str, country_code: str = "507") -> str:
        """
        Format phone number to WhatsApp format: {country_code}{number}@s.whatsapp.net

        Args:
            phone: Phone number (may include non-digit characters)
            country_code: Default country code (default: 507 for Panama)

        Returns:
            Formatted phone number in WhatsApp format

        Example:
            >>> WhapifyRepository.format_phone_number("55 1234 5678")
            "50755123456780@s.whatsapp.net"
            >>> WhapifyRepository.format_phone_number("+52 55 1234 5678")
            "5215512345678@s.whatsapp.net"
        """
        # Remove any non-digit characters
        clean_phone = ''.join(filter(str.isdigit, phone))

        # Ensure it starts with country code
        if not clean_phone.startswith(country_code):
            clean_phone = country_code + clean_phone

        return f"{clean_phone}@s.whatsapp.net"
