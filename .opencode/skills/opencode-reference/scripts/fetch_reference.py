#!/usr/bin/env python3
import sys
import urllib.request
from datetime import date
from pathlib import Path

DOCS_URL = "https://opencode.ai/docs/"
REFERENCES_PATH = Path(__file__).resolve().parent.parent / "references"


def update_reference(page):
    request = urllib.request.Request(
        f"{DOCS_URL}{page}",
        headers={
            "Accept": "text/markdown",
            "User-Agent": "MMM-opencode-reference-fetcher",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        markdown = response.read().decode("utf-8")
    reference_path = REFERENCES_PATH / f"{page}.md"
    reference_path.parent.mkdir(parents=True, exist_ok=True)
    reference_path.write_text(
        f"Fetched {date.today().isoformat()} from {DOCS_URL}{page}\n\n{markdown}",
        encoding="utf-8",
    )
    print(f"Updated {reference_path} from {DOCS_URL}{page}")


if __name__ == "__main__":
    update_reference(sys.argv[1] if len(sys.argv) > 1 else "agents")
