import os
import json
import socket
import threading
import uuid
from datetime import datetime, timezone

import boto3
import requests
from boto3.dynamodb.conditions import Key
from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from auth import get_current_user
from graph import build_graph

app = FastAPI()

table = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1")).Table(os.environ["TABLE_NAME"])


def get_instance_id():
    try:
        token = requests.put(
            "http://169.254.169.254/latest/api/token",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"},
            timeout=2,
        ).text
        return requests.get(
            "http://169.254.169.254/latest/meta-data/instance-id",
            headers={"X-aws-ec2-metadata-token": token},
            timeout=2,
        ).text
    except Exception:
        return socket.gethostname()


@app.get("/health")
def health():
    return {"status": "ok", "instance": get_instance_id()}


class TripRequest(BaseModel):
    origin: str
    destination: str
    startDate: str
    endDate: str
    budget: str | None = None
    interests: list[str] = []


def run_trip(payload, trip_id):
    try:
        graph = build_graph()
        graph.invoke(payload)
    except Exception as exc:
        table.update_item(
            Key={"tripId": trip_id},
            UpdateExpression="SET #st = :failed, errorMessage = :e",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={":failed": "FAILED", ":e": str(exc)},
        )


@app.post("/api/trip")
def start_trip(body: TripRequest, user_id: str = Depends(get_current_user)):
    origin = body.origin.strip()
    destination = body.destination.strip()
    if not origin or not destination or not body.startDate or not body.endDate:
        raise HTTPException(status_code=400, detail="origin, destination, startDate and endDate are required")

    trip_id = str(uuid.uuid4())
    table.put_item(Item={
        "tripId": trip_id,
        "userId": user_id,
        "origin": origin,
        "destination": destination,
        "startDate": body.startDate,
        "endDate": body.endDate,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "status": "RUNNING",
        "currentStep": "planner",
    })

    payload = {
        "trip_id": trip_id,
        "origin": origin,
        "destination": destination,
        "start_date": body.startDate,
        "end_date": body.endDate,
        "budget": body.budget,
        "interests": body.interests,
    }
    threading.Thread(target=run_trip, args=(payload, trip_id), daemon=True).start()

    return {"tripId": trip_id}


@app.get("/api/trip/{trip_id}")
def get_trip(trip_id: str, user_id: str = Depends(get_current_user)):
    item = table.get_item(Key={"tripId": trip_id}).get("Item")
    if not item or item.get("userId") != user_id:
        raise HTTPException(status_code=404, detail="Trip not found")

    result = json.loads(item["itinerary"]) if item.get("itinerary") else None
    return {
        "tripId": trip_id,
        "status": item.get("status"),
        "currentStep": item.get("currentStep"),
        "result": result,
    }


@app.get("/api/trips")
def list_trips(user_id: str = Depends(get_current_user)):
    resp = table.query(
        IndexName="UserTripsIndex",
        KeyConditionExpression=Key("userId").eq(user_id),
        ScanIndexForward=False,
    )
    trips = [{
        "tripId": i["tripId"],
        "origin": i.get("origin"),
        "destination": i.get("destination"),
        "startDate": i.get("startDate"),
        "endDate": i.get("endDate"),
        "status": i.get("status"),
        "createdAt": i.get("createdAt"),
    } for i in resp.get("Items", [])]
    return {"trips": trips}


app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")