import httpx
from typing import Any, Dict, List
from .base import BaseIngestion

class DraftKingsIngestion(BaseIngestion):
    """
    Ingests salary and slate data from DraftKings.
    """
    
    BASE_URL = "https://api.draftkings.com/draftgroups/v1"

    def __init__(self, sport: str = "NFL"):
        super().__init__(f"DraftKings-{sport}")
        self.sport = sport

    async def fetch(self) -> Dict[str, Any]:
        """
        Fetches active draft groups (slates) for the sport.
        """
        async with httpx.AsyncClient() as client:
            # Step 1: Get list of active slates (DraftGroups)
            response = await client.get(f"{self.BASE_URL}/draftgroups?sport={self.sport}")
            response.raise_for_status()
            data = response.json()
            
            slates = data.get("draftGroups", [])
            if not slates:
                return {}

            # Step 2: Fetch details (players) for the Main Slate (or first available for MVP)
            # In a real app, we'd loop through all relevant slates.
            # For MVP, let's try to find the "Main" slate or just pick the first one.
            target_slate = slates[0] 
            draft_group_id = target_slate["draftGroupId"]
            
            self.logger.info(f"Fetching details for slate ID: {draft_group_id}")
            
            details_response = await client.get(f"{self.BASE_URL}/draftgroups/{draft_group_id}/draftables")
            details_response.raise_for_status()
            
            return {
                "slate_info": target_slate,
                "players": details_response.json().get("draftables", [])
            }

    async def transform(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Transforms DK API response into a flat list of player records.
        """
        if not raw_data:
            return []
            
        slate_info = raw_data["slate_info"]
        players = raw_data["players"]
        
        transformed_data = []
        
        for p in players:
            # Basic transformation
            player_record = {
                "external_player_id": p.get("playerId"),
                "name": f"{p.get('firstName')} {p.get('lastName')}",
                "position": p.get("position"),
                "team": p.get("teamAbbreviation"),
                "salary": p.get("salary"),
                "game_time": p.get("competition", {}).get("startTime"),
                "opponent": p.get("competition", {}).get("opponentAbbreviation"), # This might need better parsing
                "slate_id": slate_info.get("draftGroupId"),
                "source": "DraftKings"
            }
            transformed_data.append(player_record)
            
        return transformed_data

    async def load(self, data: List[Dict[str, Any]]) -> int:
        """
        Placeholder load function. 
        In the next phase, this will write to the Postgres DB.
        """
        # For now, just log the count
        self.logger.info(f"Would load {len(data)} records to DB.")
        # TODO: Implement DB saving logic
        return len(data)
