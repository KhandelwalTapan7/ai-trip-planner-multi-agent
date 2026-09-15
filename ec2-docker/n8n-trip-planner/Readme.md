# Trip Planner - n8n standalone experiment

This is a completely separate copy of the 5-agent trip planner, rebuilt in n8n
instead of Python/LangGraph. It does NOT touch or depend on your existing
`ec2-docker` app in any way - different folder, different Docker network,
different ports, different Postgres volume.

Ports used here (chosen to avoid clashing with the other stack):
- n8n UI:        http://localhost:5679
- Postgres:      localhost:5433 (only needed if you want to inspect it directly)

## Setup

1. Copy `.env.example` to `.env` and fill in your real Groq API key:
   ```
   cp .env.example .env
   ```

2. Start the stack:
   ```
   docker compose up -d
   ```
   This starts Postgres (with the `trips` table auto-created from `init.sql`)
   and n8n.

3. Open n8n at http://localhost:5679 and create a local admin account
   (first-run setup, stored only in this container's volume).

4. Import the workflow:
   - Menu (☰) -> Import from File -> select `trip_planner_workflow.json`

5. Set up the Postgres credential on the "Save Itinerary to Postgres" node:
   - Host: `db`
   - Port: `5432`
   - Database: `trip_planner`
   - User: `trip_planner`
   - Password: `trip_planner`
   - SSL: disable

6. Activate the workflow (toggle switch, top right, to "Active"). This
   registers the webhook at:
   `http://localhost:5679/webhook/trip`

## Testing it (no frontend needed)

Trigger a trip plan directly with curl:

```bash
curl -X POST http://localhost:5679/webhook/trip \
  -H "Content-Type: application/json" \
  -d '{
    "trip_id": "11111111-1111-1111-1111-111111111111",
    "origin": "Jaipur",
    "destination": "Chandigarh",
    "start_date": "2026-10-01",
    "end_date": "2026-10-05",
    "budget": "20000",
    "interests": ["food", "heritage"],
    "travelers": 2
  }'
```

Note: the `trips` row must exist before the workflow can save to it (the
workflow only UPDATEs, it doesn't INSERT). Create the row first:

```bash
docker compose exec db psql -U trip_planner -d trip_planner -c \
  "INSERT INTO trips (trip_id, user_id, origin, destination, start_date, end_date, travelers, status) \
   VALUES ('11111111-1111-1111-1111-111111111111', 'test-user', 'Jaipur', 'Chandigarh', '2026-10-01', '2026-10-05', 2, 'RUNNING');"
```

Then run the curl command above, wait ~15-30 seconds (5 Groq calls happen
in sequence), and check the result:

```bash
docker compose exec db psql -U trip_planner -d trip_planner -c \
  "SELECT status, itinerary FROM trips WHERE trip_id = '11111111-1111-1111-1111-111111111111';"
```

## What this does NOT include (by design, kept minimal)

- No login/auth - it's just the agent pipeline, triggered directly via webhook
- No frontend - test via curl or n8n's own "Test workflow" button
- No live step-by-step status updates (jumps straight to SUCCEEDED)
- No automatic FAILED status if a Groq call errors mid-workflow (visible in
  n8n's execution log though, under "Executions" in the left sidebar)

This is meant as a sandbox to see the same agent logic running in n8n. If you
like it and want to actually wire it into the main app later, that's a
separate, deliberate integration step - not automatic.