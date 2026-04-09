from supabase import create_client, Client
from utils.config import settings
from utils.logger import get_logger

logger = get_logger("supabase")

class SupabaseClient:
    def __init__(self):
        self.client: Client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_KEY
        )
        logger.info("Supabase client initialized")

    def insert(self, table: str, data: dict):
        try:
            res = self.client.table(table).insert(data).execute()
            return res.data
        except Exception as e:
            logger.error(f"Insert error: {e}")
            return None

    def query(self, table: str, filters: dict):
        try:
            q = self.client.table(table).select("*")
            for k, v in filters.items():
                q = q.eq(k, v)
            return q.execute().data
        except Exception as e:
            logger.error(f"Query error: {e}")
            return None

    def rpc(self, fn: str, params: dict):
        try:
            return self.client.rpc(fn, params).execute().data
        except Exception as e:
            logger.error(f"RPC error: {e}")
            return None


supabase_client = SupabaseClient()