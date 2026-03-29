from massive import WebSocketClient
from massive.websocket.models import WebSocketMessage, Feed, Market
from typing import List
from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv(Path(__file__).parent / ".env")


client = WebSocketClient(
	api_key=os.getenv("MASSIVE_API_KEY"),
	feed=Feed.Delayed,
	market=Market.Stocks
	)

# aggregates (per second)
client.subscribe("A.SPY")

def handle_msg(msgs: List[WebSocketMessage]):
    for m in msgs:
        print(m)

# print messages
client.run(handle_msg)
