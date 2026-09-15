import boto3
import json

table = boto3.resource("dynamodb", region_name="us-east-1").Table("trip-planner-sessions")

resp = table.scan()
items = resp.get("Items", [])
failed = [i for i in items if i.get("status") == "FAILED"]
failed.sort(key=lambda i: i.get("createdAt", ""), reverse=True)

if failed:
    print(json.dumps(failed[0], indent=2, default=str))
else:
    print("No failed trips found.")