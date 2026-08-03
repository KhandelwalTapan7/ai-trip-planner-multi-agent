import json
import os
import boto3
from boto3.dynamodb.conditions import Key

table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])

CORS_HEADERS = {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}


def lambda_handler(event, context):
    user_id = event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]

    resp = table.query(
        IndexName="UserTripsIndex",
        KeyConditionExpression=Key("userId").eq(user_id),
        ScanIndexForward=False,
    )

    trips = [{
        "tripId": item["tripId"],
        "origin": item.get("origin"),
        "destination": item.get("destination"),
        "startDate": item.get("startDate"),
        "endDate": item.get("endDate"),
        "status": item.get("status"),
        "createdAt": item.get("createdAt"),
    } for item in resp.get("Items", [])]

    return {"statusCode": 200, "headers": CORS_HEADERS, "body": json.dumps({"trips": trips})}