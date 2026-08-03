import json
import os
import boto3

table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])

CORS_HEADERS = {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}


def lambda_handler(event, context):
    user_id = event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]
    trip_id = event["pathParameters"]["tripId"]

    item = table.get_item(Key={"tripId": trip_id}).get("Item")
    if not item or item.get("userId") != user_id:
        return {"statusCode": 404, "headers": CORS_HEADERS, "body": json.dumps({"error": "Trip not found"})}

    result = json.loads(item["itinerary"]) if item.get("itinerary") else None

    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({
            "tripId": trip_id,
            "status": item.get("status"),
            "currentStep": item.get("currentStep"),
            "result": result,
        }),
    }
