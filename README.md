# AI Trip Planner (Multi-Agent) — "Field Itinerary"

A trip planner where five AI agents genuinely collaborate — three of them running
in parallel — to turn an origin, a destination, dates, a budget, and a few
interests into a detailed, day-by-day itinerary with real place names, a cost
breakdown in ₹, and multi-modal transport options. Built with
[LangGraph](https://github.com/langchain-ai/langgraph) and
[Groq](https://console.groq.com), deployed on AWS **three different ways**, all
sharing the same login system and trip history.

```
Traveler → Sign in (Cognito) → 5-agent LangGraph pipeline → DynamoDB → Result
```

## What it does

- **Planner agent** drafts a rough day-by-day skeleton
- **Budget**, **Local info**, and **Transport** agents run *at the same time* —
  none of them depend on each other, only on the planner's output
- **Writer agent** waits for all three, then produces the final itinerary:
  4–6 time-blocked activities per day using real named places, a budget
  breakdown, and flight/train/bus/self-drive options
- Live "agent ledger" in the UI shows which agent is currently working — it's
  reading real execution state from the database, not a fake progress bar
- Full auth (Cognito) with a persistent, per-user **trip history**
- Everything costs ₹ and is written with Indian travelers in mind

## Three deployments, one shared backend

| | Compute | How requests are authenticated | How the async job starts |
|---|---|---|---|
| **Serverless** | 4 AWS Lambda functions behind API Gateway | API Gateway's built-in Cognito JWT authorizer | One Lambda asynchronously invokes another |
| **Single container** | One FastAPI app in Docker, on one EC2 instance | App verifies Cognito JWTs itself via JWKS | A background Python thread |
| **Load-balanced** | Two EC2 instances (cloned via AMI) behind an Application Load Balancer | Same as above, on both instances | Same as above, on whichever instance answers |

All three talk to the **same** DynamoDB table and Cognito User Pool — a trip
planned on one shows up in "My Trips" on all of them.

## Repo structure

```
trip-planner/
  backend/                        Serverless deployment (SAM)
    template.yaml                 Every AWS resource, as code
    functions/
      start_trip/                 POST /trip -> creates the record, kicks off the graph
      get_trip_status/            GET /trip/{id} -> status, current agent, result
      list_trips/                 GET /trips -> a user's trip history (queries a GSI)
      trip_orchestrator/
        app.py                    Lambda entrypoint
        graph.py                  The LangGraph StateGraph and all 5 agent nodes
        groq_client.py            Shared LLM call helper, with retry-on-429
        weather_client.py         Open-Meteo geocoding + forecast (free, no key)
  frontend/
    index.html                    Single-file UI: auth, trip form, live ledger, results, trip history
  ec2-docker/                     Containerized deployment (see its own README.md)
    app/                          Same agents, wrapped in one FastAPI app
    frontend/                     Same UI, pointed at a same-origin API
    Dockerfile, docker-compose.yml
    ec2-dynamodb-policy.json      IAM policy for the EC2 instance role
```

## The agent graph

```python
graph.set_entry_point("planner")
graph.add_edge("planner", "budget")
graph.add_edge("planner", "local_info")
graph.add_edge("planner", "transport")
graph.add_edge("budget", "writer")
graph.add_edge("local_info", "writer")
graph.add_edge("transport", "writer")
graph.add_edge("writer", END)
```

LangGraph runs any node whose dependencies are satisfied within the same step —
so `budget`, `local_info`, and `transport` genuinely execute concurrently. A full
run costs roughly two rounds of LLM latency, not four, despite five agents.

## Quickstart

### Option A — Serverless (recommended starting point)

**Prerequisites:** AWS account, [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) + AWS CLI configured, Python 3.12, a free key from [console.groq.com](https://console.groq.com).

```bash
cd backend
sam build
sam deploy --guided
```

Paste your Groq key when prompted for `GroqApiKey`. Note the four outputs when
it finishes: `ApiEndpoint`, `FrontendBucketName`, `UserPoolId`, `UserPoolClientId`.

In `frontend/index.html`, replace the three placeholder constants near the
bottom with those four values, then:

```bash
aws s3 sync frontend s3://<FrontendBucketName>
```

Visit the `FrontendUrl` output, sign up (Cognito emails a confirmation code
automatically), confirm, sign in, and plan a trip.

### Option B / C — Docker on EC2, with or without a load balancer

See [`ec2-docker/README.md`](ec2-docker/README.md) for the full walkthrough —
launching an instance, IAM role setup, installing Docker, and (optionally)
cloning a second instance behind an Application Load Balancer for genuine
traffic distribution across two servers.

## What's free here

**Always free, no time limit:** Lambda (1M requests/month), DynamoDB (25GB).

**Free indefinitely:** Cognito's Essentials tier — 10,000 monthly active users,
forever, not just for 12 months.

**Free for 12 months from account creation:** S3 storage, API Gateway calls,
EC2 (750 hours/month), Application Load Balancer (750 hours/month + 15 LCUs).

**One real caveat:** EC2's free hours are *pooled across every running
instance*, not granted per instance. One instance running continuously all
month is free; two running continuously (the load-balanced setup) costs
roughly $8/month in overage.

**Not AWS, but free:** every LLM call (Groq's free tier) and all
geocoding/weather data (Open-Meteo, no key required) — this is what keeps the
project free instead of a Bedrock pay-per-token one.

## Notable engineering details

A few things worth knowing if you're reading this code, not just running it:

- **The async job pattern.** Neither deployment makes the client wait through
  a 30–60 second agent run. `start_trip` writes a DynamoDB record and returns
  a `tripId` immediately; the frontend polls every 2.5 seconds. Each agent
  writes its own name to DynamoDB as it starts, which is what actually powers
  the live ledger.
- **`list_trips` queries a GSI**, not a table scan — `UserTripsIndex` on
  `userId` / `createdAt` — the correct way to do "give me this user's rows" in
  DynamoDB.
- **Auth verification moves depending on the deployment.** API Gateway does it
  for free in the serverless version; `ec2-docker/app/auth.py` does it by hand
  (fetching Cognito's JWKS and verifying signature/issuer/audience) when
  there's no API Gateway in front.
- **Containers need an explicit AWS region.** `boto3.resource("dynamodb")`
  with no `region_name` throws `NoRegionError` inside Docker, even with
  `AWS_REGION` set as an env var — unlike Lambda, which knows its region
  automatically. Fixed by passing `region_name` explicitly everywhere.
- **An AMI clones more than the OS.** Cloning a working EC2 instance to make
  a second load-balancer target also cloned the *running Docker container's
  identity* — both instances briefly reported the same container ID on their
  health checks. Fixed by identifying instances via EC2 instance metadata
  (IMDS) instead of asking Docker.
- **Free-tier LLM rate limits are a shared budget across a burst of
  requests**, not a per-call limit — `groq_client.py` retries with backoff on
  429s, and each agent's `max_tokens` is sized to what it actually needs
  instead of one generous number everywhere.

## Auth notes

This is intentionally a basic setup — the ID token lives in `localStorage`
with no refresh handling, so sessions expire after about an hour. A
production version would use the refresh token and a more careful storage
strategy (e.g. an HttpOnly cookie via a small backend proxy).

## Cleaning up

```bash
# Serverless
aws s3 rm s3://<FrontendBucketName> --recursive
cd backend && sam delete

# EC2 / Docker
# Terminate both instances from the EC2 console, and delete the
# Load Balancer + Target Group if you built the load-balanced version.
```

## Putting this on a resume

Specific, honest bullet points this project actually supports:

- Built a 5-agent multi-agent system with LangGraph, orchestrating a
  parallel fan-out/fan-in graph (3 concurrent agents merging into one),
  powered by Groq
- Deployed the same application three ways on AWS — serverless (Lambda,
  API Gateway, DynamoDB, Cognito), containerized (Docker on EC2), and
  load-balanced (two EC2 instances behind an Application Load Balancer with
  custom health checks)
- Implemented JWT authentication two ways: via an API Gateway Cognito
  authorizer, and manually via JWKS verification in a framework with no
  built-in equivalent
- Designed an async job pattern (write-then-poll, with live per-agent status)
  to work around both API Gateway's 30-second timeout and long-running
  synchronous requests in general
- Debugged infrastructure-level issues distinct from application bugs: an
  IAM permissions boundary vs. policy misconfiguration, a missing Cognito
  auth flow, container region resolution, AMI-cloned container identity, and
  EC2 instance metadata hop limits

## Next steps

- CloudFront in front of the S3 frontend for real HTTPS
- Refresh-token handling so sessions don't expire after an hour
- A cyclical graph edge: writer back to planner if the budget agent flags a
  trip as badly over budget, instead of a strictly linear pipeline