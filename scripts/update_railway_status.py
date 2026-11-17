#!/usr/bin/env python3
"""Fail-closed Railway deployment snapshot publisher. Requires RAILWAY_API_TOKEN.
Never publishes credentials, runtime logs, or trading account information.
"""
import datetime as dt
import json
import os
import pathlib
import sys
import urllib.request

PROJECT_ID = "d6b28c6e-38e4-4e15-a9b2-0686d2fa17e9"
ENDPOINT = "https://backboard.railway.com/graphql/v2"
OUTPUT = pathlib.Path("railway-status.json")
QUERY = """query DeploymentEvidence($projectId: String!) {
  project(id: $projectId) {
    name
    services {
      edges { node { id name } }
    }
  }
  deployments(input: { projectId: $projectId }, first: 50) {
    edges {
      node {
        id
        serviceId
        status
        createdAt
      }
    }
  }
}"""

def main():
    token = os.environ.get("RAILWAY_API_TOKEN", "")
    if not token:
        print("RAILWAY_API_TOKEN is missing; leaving prior snapshot unchanged.")
        return 2
    payload = json.dumps({"query": QUERY, "variables": {"projectId": PROJECT_ID}}).encode()
    request = urllib.request.Request(ENDPOINT, data=payload, headers={
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "User-Agent": "cipher-hq-readonly-status/1.0",
    })
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.load(response)
        if result.get("errors"):
            raise ValueError("Railway GraphQL rejected status query")
        project = result["data"]["project"]
        service_edges = project["services"]["edges"]
        deployments = result["data"]["deployments"]["edges"]
        newest = {}
        for edge in deployments:
            d = edge["node"]
            sid = d.get("serviceId")
            if sid and (sid not in newest or d["createdAt"] > newest[sid]["createdAt"]):
                newest[sid] = d
        services = []
        for edge in service_edges:
            svc = edge["node"]
            deployment = newest.get(svc["id"])
            services.append({
                "name": svc["name"],
                "repository": None,
                "branch": None,
                "deployment_status": deployment["status"] if deployment else "UNKNOWN",
                "deployed_at": deployment["createdAt"] if deployment else None,
            })
        if not services:
            raise ValueError("No services returned; refusing to overwrite evidence")
        data = {
            "schema": 1,
            "source": "Railway GraphQL deployment metadata (scheduled)",
            "project": project["name"],
            "environment": "project-wide (not production-filtered)",
            "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "services": services,
        }
        OUTPUT.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print("Wrote sanitized deployment evidence for", len(services), "services")
        return 0
    except Exception as exc:
        print("Railway query failed; previous evidence preserved:", type(exc).__name__)
        return 1

if __name__ == "__main__":
    sys.exit(main())
