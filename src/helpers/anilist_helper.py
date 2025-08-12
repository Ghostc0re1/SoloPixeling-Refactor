import httpx
import os


async def anilist_exchange_code(code: str):
    async with httpx.AsyncClient(timeout=10) as x:
        r = await x.post(
            "https://anilist.co/api/v2/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": os.getenv("AL_CLIENT_ID"),
                "client_secret": os.getenv("AL_CLIENT_SECRET"),
                "redirect_uri": "https://your-domain.com/oauth/anilist/callback",
                "code": code,
            },
        )
        r.raise_for_status()
        return r.json()  # { access_token, token_type, expires_in, refresh_token }
