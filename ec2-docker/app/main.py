import json
import socket
import threading
import uuid
from datetime import date

import requests
from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
from auth import get_current_user, hash_password, verify_password, create_token
from graph import build_graph

app = FastAPI()

db.init_db()


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


class SignupRequest(BaseModel):
    email: str
    password: str


class SigninRequest(BaseModel):
    email: str
    password: str


@app.post("/api/auth/signup")
def signup(body: SignupRequest):
    email = body.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="A valid email is required")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    if db.get_user_by_email(email):
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    user = db.create_user(email, hash_password(body.password))
    token = create_token(user["user_id"], user["email"])
    return {"token": token, "email": user["email"]}


@app.post("/api/auth/signin")
def signin(body: SigninRequest):
    email = body.email.strip().lower()
    user = db.get_user_by_email(email)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    token = create_token(user["user_id"], user["email"])
    return {"token": token, "email": user["email"]}


class TripRequest(BaseModel):
    origin: str
    destination: str
    startDate: str
    endDate: str
    budget: str | None = None
    interests: list[str] = []
    travelers: int = 1


def run_trip(payload, trip_id):
    try:
        graph = build_graph()
        graph.invoke(payload)
    except Exception as exc:
        db.mark_failed(trip_id, str(exc))


@app.post("/api/trip")
def start_trip(body: TripRequest, user_id: str = Depends(get_current_user)):
    origin = body.origin.strip()
    destination = body.destination.strip()
    if not origin or not destination or not body.startDate or not body.endDate:
        raise HTTPException(status_code=400, detail="origin, destination, startDate and endDate are required")

    try:
        start = date.fromisoformat(body.startDate)
        end = date.fromisoformat(body.endDate)
    except ValueError:
        raise HTTPException(status_code=400, detail="startDate and endDate must be valid YYYY-MM-DD dates")

    if start < date.today():
        raise HTTPException(status_code=400, detail="Start date can't be in the past")
    if end < start:
        raise HTTPException(status_code=400, detail="End date must be on or after the start date")

    travelers = max(1, min(body.travelers or 1, 20))

    trip_id = str(uuid.uuid4())
    db.create_trip(trip_id, user_id, origin, destination, body.startDate, body.endDate, travelers)

    payload = {
        "trip_id": trip_id,
        "origin": origin,
        "destination": destination,
        "start_date": body.startDate,
        "end_date": body.endDate,
        "budget": body.budget,
        "interests": body.interests,
        "travelers": travelers,
    }
    threading.Thread(target=run_trip, args=(payload, trip_id), daemon=True).start()

    return {"tripId": trip_id}


@app.get("/api/trip/{trip_id}")
def get_trip(trip_id: str, user_id: str = Depends(get_current_user)):
    item = db.get_trip(trip_id)
    if not item or item.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Trip not found")

    result = item["itinerary"] if item.get("itinerary") else None
    if isinstance(result, str):
        result = json.loads(result)
    return {
        "tripId": trip_id,
        "status": item.get("status"),
        "currentStep": item.get("current_step"),
        "result": result,
    }


@app.get("/api/trips")
def list_trips(user_id: str = Depends(get_current_user)):
    items = db.list_trips(user_id)
    trips = [{
        "tripId": str(i["trip_id"]),
        "origin": i.get("origin"),
        "destination": i.get("destination"),
        "startDate": i["start_date"].isoformat() if i.get("start_date") else None,
        "endDate": i["end_date"].isoformat() if i.get("end_date") else None,
        "status": i.get("status"),
        "createdAt": i["created_at"].isoformat() if i.get("created_at") else None,
    } for i in items]
    return {"trips": trips}


app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
