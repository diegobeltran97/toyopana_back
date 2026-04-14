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
                    array_value
                    date_value
                    datetime_value
                    float_value
                    report_value
                    filled_at
                    updated_at
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

    async def get_all_cards_in_phase(
        self,
        phase_id: str,
        first: int = 50,
        after: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get all cards in a specific phase using GraphQL pagination

        Args:
            phase_id: The Pipefy phase ID
            first: Number of cards to fetch per page (default 50, max 50)
            after: Cursor for pagination (optional)

        Returns:
            Dictionary containing cards array, phase info, and pagination info

        Example response:
            {
                "phase_id": "341972150",
                "phase_name": "In Progress",
                "cards_count": 125,
                "cards": [...],
                "pageInfo": {
                    "hasNextPage": true,
                    "endCursor": "xyz123"
                }
            }
        """
        query = """
        query GetPhaseCards($phaseId: ID!, $first: Int!, $after: String) {
            phase(id: $phaseId) {
                id
                name
                cards_count
                fields {
                    id
                    label
                    type
                }
                cards(first: $first, after: $after) {
                    edges {
                        node {
                            id
                            title
                            createdAt
                            due_date
                            url
                            current_phase {
                                id
                                name
                            }
                            fields {
                                name
                                value
                                array_value
                                date_value
                                datetime_value
                                float_value
                                report_value
                                filled_at
                                updated_at
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
                            }
                            pipe {
                                id
                                name
                            }
                        }
                    }
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                }
            }
        }
        """

        variables = {
            "phaseId": phase_id,
            "first": min(first, 50)  # Pipefy max is 50
        }

        if after:
            variables["after"] = after

        result = await self._execute_query(query, variables)
        phase_data = result.get("phase", {})
        cards_data = phase_data.get("cards", {})

        # Extract cards from edges
        cards = [edge["node"] for edge in cards_data.get("edges", [])]

        return {
            "phase_id": phase_data.get("id"),
            "phase_name": phase_data.get("name"),
            "cards_count": phase_data.get("cards_count"),
            "phase_fields": phase_data.get("fields", []),
            "cards": cards,
            "pageInfo": cards_data.get("pageInfo", {})
        }

    async def save_webhook_event(self, event_data: dict):
        """Save webhook event data to database (placeholder)"""
        print(f"Saving webhook event: {event_data}")