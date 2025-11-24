import os
import time
import asyncio
from typing import List, Dict
from dotenv import load_dotenv
from google import genai

# Load environment variables
# Prefer .env.local if it exists, otherwise .env
if os.path.exists(".env.local"):
    load_dotenv(".env.local")
else:
    load_dotenv()

class Settings:
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/ugc")
    APP_SECRET = os.getenv("APP_SECRET", "dev-secret")
    REFRESH_TOKEN_SECONDS = int(os.getenv("REFRESH_TOKEN_SECONDS", 60 * 60 * 24 * 30))
    GEMINI_API_KEYS = os.getenv("GEMINI_API_KEYS", "")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

settings = Settings()

class KeyManager:
    def __init__(self):
        keys_str = settings.GEMINI_API_KEYS
        if not keys_str:
            single_key = settings.GEMINI_API_KEY
            raw_keys = [single_key] if single_key else []
        else:
            raw_keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        
        self.keys = [{"key": k, "next_allowed": 0} for k in raw_keys]
        self.index = 0
        self._lock = asyncio.Lock()

    async def get_client(self) -> genai.Client:
        async with self._lock:
            if not self.keys:
                # Fallback or error if no keys. 
                # If no keys provided, maybe user relies on ADC (Application Default Credentials)?
                # But for this specific requirement, we expect keys.
                raise ValueError("No GEMINI_API_KEYS found in environment!")
            
            idx = self.index
            self.index = (self.index + 1) % len(self.keys)
            item = self.keys[idx]
            
            now = time.time()
            wait_time = 0
            if item["next_allowed"] > now:
                wait_time = item["next_allowed"] - now
            
            effective_start = max(now, item["next_allowed"])
            # Rate limit: 1 request per 10 seconds per key (conservative)
            # Adjust as needed. The user's script used 10s.
            item["next_allowed"] = effective_start + 10 
            
            key = item["key"]

        if wait_time > 0:
            await asyncio.sleep(wait_time)
            
        return genai.Client(api_key=key)

    async def get_api_key(self) -> str:
        async with self._lock:
            if not self.keys:
                raise ValueError("No GEMINI_API_KEYS found in environment!")
            
            idx = self.index
            self.index = (self.index + 1) % len(self.keys)
            item = self.keys[idx]
            
            now = time.time()
            wait_time = 0
            if item["next_allowed"] > now:
                wait_time = item["next_allowed"] - now
            
            effective_start = max(now, item["next_allowed"])
            # Rate limit: 1 request per 10 seconds per key (conservative)
            item["next_allowed"] = effective_start + 10 
            
            key = item["key"]

        if wait_time > 0:
            await asyncio.sleep(wait_time)
            
        return key

# Global KeyManager instance
key_manager = KeyManager()
