"""Startup warm-up: load the model and pre-write recent stories in the background.

A local model's first request is slow (loading weights), and each month's story is
generated on first view. Doing both at startup means the first customer of the day
sees the story immediately. Progress is reported by GET /api/health.
"""

import logging
import threading
import time

from ai.storyteller import generate_story
from analytics.budgets import without_existing_budget_advice
from analytics.insights import build_facts, comparable_months
from repository import Repository
from tenants import load_tenants

logger = logging.getLogger(__name__)

WARM_MONTHS = 2  # the latest months are what customers open first

state: dict = {"status": "idle", "stories_ready": 0, "stories_total": 0, "seconds": None, "error": None}


def warm_up(repo: Repository, customer_ref: str) -> None:
    started = time.perf_counter()
    state.update(status="running", stories_ready=0, stories_total=0, error=None)
    try:
        tenants = [t for t in load_tenants().values() if t.features.get("story", True)]
        for tenant in tenants:
            customer = repo.find_customer(tenant.id, customer_ref)
            if customer is None:
                continue  # bank without demo data yet
            df = repo.transactions(customer)
            budgets = repo.budgets(customer)
            months = comparable_months(df)[-WARM_MONTHS:]
            state["stories_total"] += len(months)
            for month in months:
                facts = without_existing_budget_advice(build_facts(df, month), budgets)
                story = generate_story(facts)  # cached, so identical facts across banks are written once
                if not story["ai_available"]:
                    raise RuntimeError("language model is not reachable")
                state["stories_ready"] += 1

        state["status"] = "ready"
    except Exception as exc:  # never crash the API because warm-up failed
        logger.warning("Warm-up failed: %s", exc)
        # /api/health is public: report the kind of failure, keep details (SQL, hosts) in the server log.
        state.update(status="failed", error=type(exc).__name__)
    finally:
        state["seconds"] = round(time.perf_counter() - started, 1)
        logger.info("Warm-up %s in %ss (%s stories)", state["status"], state["seconds"], state["stories_ready"])


def start_in_background(repo: Repository, customer_ref: str) -> None:
    threading.Thread(target=warm_up, args=(repo, customer_ref), daemon=True, name="narrai-warmup").start()
