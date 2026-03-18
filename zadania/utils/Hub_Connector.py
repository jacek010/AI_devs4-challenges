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
        print(f"Sending verification request to {url} with payload: \n{payload} \n\n")
        response = requests.post(url, json=payload)
        try:
            body = response.json()
        except Exception:
            body = response.text
        print(f"Response CODE: {response.status_code} | BODY: {body} \n\n")
        return body

    def receive_data(self, endpoint: str, authorize: bool = True, type = "get"):
        url = f"{self.base_url}{endpoint}"
        if authorize:
            url = f"{self.base_url}/data/{self.api_key}{endpoint}"
        else:
            url = f"{self.base_url}/data{endpoint}"
        response = None 
        if type == "get":
            response = requests.get(url)
        elif type == "post":
            response = requests.post(url)
        else:            
            raise ValueError("Unsupported request type")
        response.raise_for_status()
        return response
    
    def api_post_request(self, endpoint: str, data: dict):
        url = f"{self.base_url}/api{endpoint}"
        data["apikey"] = self.api_key
        response = requests.post(url, json=data)
        response.raise_for_status()
        return response.json()