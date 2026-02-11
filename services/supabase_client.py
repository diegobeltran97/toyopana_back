"""
Supabase Database Client

This module creates a Supabase client that we'll use to interact with our database.

Why we need this:
- The Supabase library provides an easy interface to query our PostgreSQL database
- We configure it once here and reuse it across the app
- It handles authentication automatically using our service role key
"""

from supabase import create_client, Client
from core.config import settings


def get_supabase_client() -> Client:
    """
    Creates and returns a Supabase client instance.

    This function:
    1. Takes your SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY from settings
    2. Creates a client that can query your database
    3. Returns it for use in repositories/services

    Returns:
        Client: Configured Supabase client ready to use
    """
    return create_client(
        supabase_url=settings.SUPABASE_URL,
        supabase_key=settings.SUPABASE_SERVICE_ROLE_KEY
    )


# Create a singleton instance
# This means we create ONE client that gets reused everywhere
# More efficient than creating a new client for every request
supabase_client = get_supabase_client()
