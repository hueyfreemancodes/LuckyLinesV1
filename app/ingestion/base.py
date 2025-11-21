from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import logging
import asyncio
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BaseIngestion(ABC):
    """
    Abstract base class for all data ingestion sources.
    Enforces a standard Fetch -> Transform -> Load pipeline.
    Includes error handling and 'Dead Man's Switch' hooks.
    """

    def __init__(self, source_name: str):
        self.source_name = source_name
        self.logger = logging.getLogger(f"ingestion.{source_name}")

    @abstractmethod
    async def fetch(self) -> Any:
        """
        Retrieve raw data from the external source (API, Scraper, etc.).
        Should raise an exception if data cannot be retrieved.
        """
        pass

    @abstractmethod
    async def transform(self, raw_data: Any) -> List[Dict[str, Any]]:
        """
        Clean and normalize the raw data into a standard format.
        """
        pass

    @abstractmethod
    async def load(self, data: List[Dict[str, Any]]) -> int:
        """
        Save the transformed data to the database/cache.
        Returns the number of records saved.
        """
        pass

    async def run(self) -> Dict[str, Any]:
        """
        Execute the full ingestion pipeline.
        """
        start_time = datetime.now()
        self.logger.info(f"Starting ingestion for {self.source_name}")

        try:
            # 1. Fetch
            raw_data = await self.fetch()
            if not raw_data:
                self.logger.warning(f"No data retrieved for {self.source_name}")
                return {"status": "warning", "message": "No data retrieved", "records": 0}

            # 2. Transform
            transformed_data = await self.transform(raw_data)
            if not transformed_data:
                self.logger.warning(f"No data after transformation for {self.source_name}")
                return {"status": "warning", "message": "No data after transformation", "records": 0}

            # 3. Load
            records_count = await self.load(transformed_data)
            
            duration = (datetime.now() - start_time).total_seconds()
            self.logger.info(f"Successfully ingested {records_count} records from {self.source_name} in {duration:.2f}s")
            
            return {
                "status": "success",
                "records": records_count,
                "duration_seconds": duration
            }

        except Exception as e:
            self.logger.error(f"Ingestion failed for {self.source_name}: {str(e)}", exc_info=True)
            await self._trigger_dead_mans_switch(str(e))
            return {
                "status": "error",
                "error": str(e)
            }

    async def _trigger_dead_mans_switch(self, error_msg: str):
        """
        Alerting mechanism for critical failures.
        In production, this would send a Slack message, PagerDuty alert, or email.
        """
        self.logger.critical(f"DEAD MAN'S SWITCH TRIGGERED for {self.source_name}: {error_msg}")
        # TODO: Implement actual notification logic (Slack/Discord webhook)
