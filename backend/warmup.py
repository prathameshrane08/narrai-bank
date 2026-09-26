"""Startup warm-up: load the model and pre-write recent stories in the background.

A local model's first request is slow (loading weights), and each month's story is
generated on first view. Doing both at startup means the first customer of the day
sees the story immediately. Progress is reported by GET /api/health.
"""

import logging
import threading
import time
from collections.abc import Callable

import pandas as pd

from ai.storyteller import generate_story
from analytics.budgets import without_existing_budget_advice
from analytics.insights import build_facts, comparable_months
from storage import BudgetStore
from tenants import load_tenants

logger = logging.getLogger(__name__)

WARM_MONTHS = 2  # the latest months are what customers open first

state: dict = {"status": "idle", "stories_ready": 0, "stories_total": 0, "seconds": None, "error": None}


def warm_up(load_data: Callable[[], pd.DataFrame], store: BudgetStore, customer: str) -> None:
    started = time.perf_counter()
    state.update(status="running", stories_ready=0, error=None)
    try:
        df = load_data()
        months = comparable_months(df)[-WARM_MONTHS:]
        tenants = [t for t in load_tenants().values() if t.features.get("story", True)]
        state["stories_total"] = len(months) * len(tenants)

        for tenant in tenants:
            budgets = store.list(tenant.id, customer)
            for month in months:
                facts = without_existing_budget_advice(build_facts(df, month), budgets)
                story = generate_story(facts)  # cached, so identical facts across banks are written once
                if not story["ai_available"]:
                    raise RuntimeError("language model is not reachable")
                state["stories_ready"] += 1

        state["status"] = "ready"
    except Exception as exc:  # never crash the API because warm-up failed
        logger.warning("Warm-up failed: %s", exc)
        state.update(status="failed", error=str(exc))
    finally:
        state["seconds"] = round(time.perf_counter() - started, 1)
        logger.info("Warm-up %s in %ss (%s stories)", state["status"], state["seconds"], state["stories_ready"])


def start_in_background(load_data: Callable[[], pd.DataFrame], store: BudgetStore, customer: str) -> None:
    threading.Thread(target=warm_up, args=(load_data, store, customer), daemon=True, name="narrai-warmup").start()
