# Trip planner — EC2 + Docker deployment

Same app, different deployment: one FastAPI server (in one Docker container)
handles both the API and the frontend, instead of Lambda + API Gateway + S3.
Uses the same DynamoDB table and Cognito User Pool as the serverless version,
so trips and accounts are shared between the two.

```
ec2-docker/
  app/
    main.py                 FastAPI routes (replaces start_trip, get_trip_status, list_trips)
    auth.py                 Verifies Cognito tokens against the User Pool's JWKS
    graph.py                same LangGraph agents, unchanged
    groq_client.py
    weather_client.py
    requirements.txt
  frontend/
    index.html               same UI, API_BASE now points to /api (same origin)
  Dockerfile
  docker-compose.yml
  ec2-dynamodb-policy.json    IAM policy for the EC2 instance role
```

## 1. Launch an EC2 instance

- AMI: Ubuntu 22.04 or Amazon Linux 2023
- Instance type: t2.micro or t3.micro (free tier eligible)
- Security group: allow inbound **port 80** (HTTP, from anywhere) and **port 22** (SSH, from your IP only)

## 2. Give the instance permission to reach DynamoDB

Don't put AWS credentials in the container. Instead:

1. IAM Console → Roles → Create role → trusted entity **EC2**
2. Create a policy from `ec2-dynamodb-policy.json` (paste its JSON into the policy editor), attach it to the role
3. Attach the role to your EC2 instance (during launch, or later via Actions → Security → Modify IAM role)

boto3 running on the instance will pick this up automatically — no keys anywhere in the code or image.

## 3. Install Docker on the instance

SSH in, then:

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-plugin
sudo usermod -aG docker $USER
newgrp docker
```

(On Amazon Linux 2023, use `sudo dnf install -y docker` and `sudo systemctl enable --now docker` instead.)

## 4. Get the code onto the instance and configure it

Copy the `ec2-docker/` folder to the instance (`scp`, `git clone`, whatever's easiest), then:

```bash
cd ec2-docker
cp .env.example .env
# edit .env: paste your real GROQ_API_KEY, USER_POOL_ID, CLIENT_ID
```

## 5. Build and run

```bash
docker compose up -d --build
```

First build installs `langgraph` and friends — give it a few minutes on a t2.micro.
If the build fails from running out of memory, add a swap file first:

```bash
sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
```

## 6. Visit it

`http://<your-ec2-public-ip>` — plain HTTP on port 80, same tradeoff as the S3 version.

## Updating after a code change

```bash
docker compose up -d --build
```

## Logs

```bash
docker compose logs -f
```

## Stopping / cleaning up

```bash
docker compose down
```

Remember to terminate the EC2 instance when you're done testing, so it doesn't
sit there past the free-tier 750 hrs/month if you're running other instances too.
