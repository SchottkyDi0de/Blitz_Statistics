from typing import Optional, Any

from pydantic import BaseModel

class DBPlayer(BaseModel):
    id: int
    nickname: str
    region: str
    premium: Optional[bool]
    premium_time: Optional[int]
    lang: Optional[str]
    last_stats: Optional[dict[str, Any]]
    image: Optional[str]