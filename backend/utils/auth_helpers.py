from utils.logger import get_logger

logger = get_logger("auth")

def get_user_from_request(request):
    """
    Placeholder: later integrate Supabase JWT
    """
    try:
        username = request.headers.get("x-username")

        if not username:
            raise Exception("Missing username")

        return username

    except Exception as e:
        logger.error(f"Auth error: {e}")
        return None