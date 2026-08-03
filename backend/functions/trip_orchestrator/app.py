from graph import build_graph, table


def lambda_handler(event, context):
    trip_id = event["trip_id"]
    try:
        graph = build_graph()
        graph.invoke(event)
    except Exception as exc:
        table.update_item(
            Key={"tripId": trip_id},
            UpdateExpression="SET #st = :failed, errorMessage = :e",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={":failed": "FAILED", ":e": str(exc)},
        )
        raise
