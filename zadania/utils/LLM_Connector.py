import os
from openai import AzureOpenAI
from typing import Optional

class AzureOpenAIConnector:
    def __init__(
        self,
        api_key: Optional[str] = None,
        azure_endpoint: Optional[str] = None,
        api_version: Optional[str] = None,
        deployment_name: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY")
        self.azure_endpoint = azure_endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
        self.api_version = api_version or os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
        self.deployment_name = deployment_name or os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

        if not self.api_key:
            raise ValueError("Azure OpenAI API key is required.")
        if not self.azure_endpoint:
            raise ValueError("Azure OpenAI endpoint is required.")
        if not self.deployment_name:
            raise ValueError("Azure OpenAI deployment name is required.")

        self.client = AzureOpenAI(
            api_key=self.api_key,
            azure_endpoint=self.azure_endpoint,
            api_version=self.api_version,
        )

    def chat_completion(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs,
    ) -> str:
        response = self.client.chat.completions.create(
            model=self.deployment_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        return response.choices[0].message.content

    def simple_prompt(
        self,
        prompt: str,
        system_message: str = "You are a helpful assistant.",
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> str:
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt},
        ]
        return self.chat_completion(messages, temperature=temperature, max_tokens=max_tokens)

    def embedding(self, text: str, embedding_deployment: Optional[str] = None) -> list[float]:
        deployment = embedding_deployment or os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002")
        response = self.client.embeddings.create(
            input=text,
            model=deployment,
        )
        return response.data[0].embedding


# Usage example:
# from utils.LLM_Connector import AzureOpenAIConnector
#
# connector = AzureOpenAIConnector()
# response = connector.simple_prompt("Tell me a joke.")
# print(response)