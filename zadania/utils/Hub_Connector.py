import os
from typing import Optional
import requests


class HubConnector:
    def __init__(
        self, 
        base_url: Optional[str] = None, 
        api_key: Optional[str] = None
    ):
        self.base_url = base_url or os.getenv("AI_DEVS4_BASE_URL")
        self.api_key = api_key or os.getenv("AI_DEVS4_API_KEY")


    def verify(self, task_name: str, data: dict, endpoint: str = "/verify"):
        url = f"{self.base_url}{endpoint}"
        payload = {
            "task": task_name,
            "apikey": self.api_key,
            "answer": data
        }
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    def receive_data(self, endpoint: str, authorize: bool = True):
        url = f"{self.base_url}{endpoint}"
        if authorize:
            url = f"{self.base_url}/data/{self.api_key}{endpoint}"
        else:
            url = f"{self.base_url}/data{endpoint}"
        response = requests.get(url)
        response.raise_for_status()
        return response