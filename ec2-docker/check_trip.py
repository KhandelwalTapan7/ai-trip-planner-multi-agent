import boto3
import json

table = boto3.resource("dynamodb", region_name="us-east-1").Table("trip-planner-sessions")

trip_id = "57dfbea3-d28d-46d5-a20f-36d4f808028c"  # replace with your trip id if needed

item = table.get_item(Key={"tripId": trip_id}).get("Item")
print(json.dumps(item, indent=2, default=str))