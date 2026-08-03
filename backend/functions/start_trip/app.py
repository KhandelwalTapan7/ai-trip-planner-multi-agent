import json
import os
import uuid
from datetime import datetime, timezone
import boto3

lambda_client = boto3.client("lambda")
table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
ORCHESTRATOR_FUNCTION = os.environ["ORCHESTRATOR_FUNCTION_NAME"]

CORS_HEADERS = {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}


def lambda_handler(event, context):
    user_id = event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]
    body = json.loads(event.get("body") or "{}")

    origin = (body.get("origin") or "").strip()
    destination = (body.get("destination") or "").strip()
    start_date = body.get("startDate")
    end_date = body.get("endDate")

    if not origin or not destination or not start_date or not end_date:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "origin, destination, startDate and endDate are required"}),
        }

    trip_id = str(uuid.uuid4())
    table.put_item(Item={
        "tripId": trip_id,
        "userId": user_id,
        "origin": origin,
        "destination": destination,
        "startDate": start_date,
        "endDate": end_date,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "status": "RUNNING",
        "currentStep": "planner",
    })

    payload = {
        "trip_id": trip_id,
        "origin": origin,
        "destination": destination,
        "start_date": start_date,
        "end_date": end_date,
        "budget": body.get("budget"),
        "interests": body.get("interests", []),
    }
    lambda_client.invoke(
        FunctionName=ORCHESTRATOR_FUNCTION,
        InvocationType="Event",
        Payload=json.dumps(payload),
    )

    return {"statusCode": 200, "headers": CORS_HEADERS, "body": json.dumps({"tripId": trip_id})}