# app/core/supabase_client.py
import os
from dotenv import load_dotenv
from supabase import create_client, Client


class SupabaseDB:
    def __init__(self):
        # Carga variables del .env
        load_dotenv()

        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not key:
            raise ValueError("SUPABASE_URL o SUPABASE_KEY no están definidos en el .env")

        # Cliente de Supabase
        self.client: Client = create_client(url, key)

    # -------- Métodos de ayuda básicos --------
    def insert(self, table: str, data: dict):
        """Inserta un registro en una tabla."""
        return self.client.table(table).insert(data).execute()

    def select_all(self, table: str):
        """Obtiene todos los registros de una tabla."""
        return self.client.table(table).select("*").execute()

    def select_filter(self, table: str, column: str, value):
        """Ejemplo de filtro simple."""
        return self.client.table(table).select("*").eq(column, value).execute()