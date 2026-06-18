import os 
from dotenv import load_dotenv

load_dotenv()

class Settings:
    PROJECT_NAME: str = "Aegis Execution Engine"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "fallback_secret_local_key")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 DAYS

settings = Settings()
                                
