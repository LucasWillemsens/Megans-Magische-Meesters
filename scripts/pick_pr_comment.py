#!/usr/bin/env python3
"""Claim one unresolved inline PR review thread and print it as JSON.

Requires an authenticated GitHub CLI (gh) and must be run from the PR checkout.
The thread is resolved before it is returned, preventing later analyst runs
from picking it up again. Errors go to stderr and use a non-zero exit status.
"""

import json
import subprocess
import sys


def gh(*args):
    result = subprocess.run(
        ["gh", *args], capture_output=True, text=True, check=False
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown gh error"
        raise RuntimeError(f"gh {' '.join(args[:2])} failed: {detail}")
    return result.stdout


def query_threads(owner, name, number):
    query = """query($owner:String!, $name:String!, $number:Int!, $cursor:String) {
      repository(owner:$owner, name:$name) {
        pullRequest(number:$number) {
          reviewThreads(first:100, after:$cursor) {
            pageInfo { hasNextPage endCursor }
            nodes { id isResolved path line originalLine comments(first:100) {
              nodes { databaseId author { login } body path line createdAt url }
            } }
          }
        }
      }
    }"""
    threads = []
    cursor = None
    while True:
        args = [
            "api", "graphql", "-f", f"query={query}",
            "-F", f"owner={owner}", "-F", f"name={name}",
            "-F", f"number={number}",
        ]
        if cursor is not None:
            args.extend(["-f", f"cursor={cursor}"])
        payload = json.loads(gh(*args))
        if payload.get("errors"):
            raise RuntimeError("GitHub GraphQL error: " + json.dumps(payload["errors"]))
        pr = payload.get("data", {}).get("repository", {}).get("pullRequest")
        if pr is None:
            raise RuntimeError("Current pull request was not found")
        connection = pr["reviewThreads"]
        threads.extend(connection["nodes"])
        if not connection["pageInfo"]["hasNextPage"]:
            return threads
        cursor = connection["pageInfo"]["endCursor"]


def is_eligible(thread):
    """Only unresolved review threads attached to a specific file line."""
    return (
        not thread["isResolved"] and bool(thread.get("path"))
        and (thread.get("line") is not None or thread.get("originalLine") is not None)
        and bool(thread.get("comments", {}).get("nodes"))
    )

def verbose_output(thread):
    print(json.dumps({
        "status": "picked",
        "thread_id": thread["id"],
        "path": thread["path"],
        "line": thread.get("line") or thread.get("originalLine"),
        "comments": thread["comments"]["nodes"],
    }))
    #example
    # {"status": "picked", "thread_id": "PRRT_kwDORO-wxc6r5FqP", "path": "roadmap/battle-page-polish/board-overflow-into-enemy-20261012/description.txt", "line": 1, "comments": [{"databaseId": 4259519370, "author": {"login": "LucasWillemsens"}, "body": "bad one", "path": "roadmap/battle-page-polish/board-overflow-into-enemy-20261012/description.txt", "line": null, "createdAt": "2026-10-13T13:54:03Z", "url": "https://github.com/LucasWillemsens/Megans-Magische-Meesters/pull/28#discussion_r4259519370"}]}
def compact_output(thread):
    print(thread["path"] +" ( ln: " + str(thread.get("line")) +"): "+ thread["comments"]["nodes"][0]["body"])
#{"path": "roadmap/battle-page-polish/hologram-flip-click-fix-20261012/description.txt", "comment": "stuff like this really should not be in the roadmap at all"}

def main():
    try:
        pr = json.loads(gh("pr", "view", "--json", "number"))
        repo = json.loads(gh("repo", "view", "--json", "owner,name"))
        owner = repo["owner"]["login"]
        name = repo["name"]
        threads = query_threads(owner, name, int(pr["number"]))
        eligible = [thread for thread in threads if is_eligible(thread)]
        if not eligible:
            print(json.dumps({"status": "no_comment"}))
            return 0

        thread = eligible[0]
        mutation = """mutation($threadId:ID!) {
          resolveReviewThread(input:{threadId:$threadId}) {
            thread { id isResolved }
          }
        }"""
        response = json.loads(gh(
            "api", "graphql", "-f", f"query={mutation}", "-F", f"threadId={thread['id']}"
        ))
        if response.get("errors"):
            raise RuntimeError("Could not claim review thread: " + json.dumps(response["errors"]))
        claimed = response.get("data", {}).get("resolveReviewThread", {}).get("thread")
        if not claimed or not claimed.get("isResolved") or claimed.get("id") != thread["id"]:
            raise RuntimeError("GitHub did not confirm the selected thread was resolved")
        
        compact_output(thread)
        return 0
    except (RuntimeError, KeyError, ValueError, TypeError) as error:
        print(json.dumps({"status": "error", "error": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
