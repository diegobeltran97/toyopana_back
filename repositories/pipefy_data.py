import httpx
from typing import Optional, Dict, Any


class PipeFyDataRepository:
    """Repository for interacting with Pipefy GraphQL API"""

    PIPEFY_GRAPHQL_ENDPOINT = "https://api.pipefy.com/graphql"

    def __init__(self, api_token: str):
        """
        Initialize Pipefy repository with API token

        Args:
            api_token: Pipefy Personal Access Token or API token
        """
        self.api_token = api_token
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }

    async def _execute_query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a GraphQL query against Pipefy API

        Args:
            query: GraphQL query string
            variables: Optional variables for the query

        Returns:
            Response data from Pipefy API

        Raises:
            httpx.HTTPError: If the request fails
        """
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.PIPEFY_GRAPHQL_ENDPOINT,
                json=payload,
                headers=self.headers,
                timeout=30.0
            )
            response.raise_for_status()
            result = response.json()

            # Check for GraphQL errors
            if "errors" in result:
                raise Exception(f"GraphQL errors: {result['errors']}")

            return result.get("data", {})

    async def get_card_details(self, card_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a card by ID

        Args:
            card_id: The Pipefy card ID

        Returns:
            Dictionary containing card details
        """
        query = """
        query GetCard($cardId: ID!) {
            card(id: $cardId) {
                id
                title
                current_phase {
                    id
                    name
                }
                fields {
                    name
                    value
                    field {
                        id
                        label
                        type
                    }
                }
                assignees {
                    id
                    name
                    email
                }
                labels {
                    id
                    name
                    color
                }
                created_at
                updated_at
                due_date
                url
            }
        }
        """

        variables = {"cardId": card_id}
        result = await self._execute_query(query, variables)

        return result.get("card", {})

    async def save_webhook_event(self, event_data: dict):
        """Save webhook event data to database (placeholder)"""
        print(f"Saving webhook event: {event_data}")