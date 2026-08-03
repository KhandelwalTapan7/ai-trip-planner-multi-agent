import os
import json
import time
import requests

GROQ_API_KEY = os.environ["GROQ_API_KEY"]
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"


def ask_json(system_prompt, user_prompt, temperature=0.4, max_tokens=3000, retries=3):
    for attempt in range(retries):
        resp = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            },
            timeout=45,
        )
        if resp.status_code == 429 and attempt < retries - 1:
            wait = float(resp.headers.get("Retry-After", 2 ** (attempt + 1)))
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return json.loads(resp.json()["choices"][0]["message"]["content"])