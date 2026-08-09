from pydantic import BaseModel

class RouteInfo(BaseModel):
    distance_meters: int
    duration_seconds: int
    mode: str
