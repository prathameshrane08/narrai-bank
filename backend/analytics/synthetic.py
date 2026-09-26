"""Seeded, realistic synthetic transactions for demos and evaluation.

Each persona has fixed costs (rent, utilities, subscriptions), variable spending
with weekend bias, occasional spending spikes and one-off unusual payments, so
the insight engine and the narrator are exercised on varied, messy months rather
than one hand-made CSV. Same persona + seed always yields the same data.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Variable:
    """A spending category with a few merchants and a typical monthly pattern."""

    merchants: tuple[str, ...]
    visits_per_month: float
    typical_amount: float
    weekend_bias: float = 0.5  # probability a visit happens on a weekend


@dataclass(frozen=True)
class Persona:
    name: str
    salary: float
    employer: str
    fixed: dict[str, tuple[str, float, int]]  # category -> (merchant, amount, day of month)
    subscriptions: tuple[tuple[str, float, int], ...]
    variable: dict[str, Variable] = field(default_factory=dict)


PERSONAS: dict[str, Persona] = {
    "young_professional": Persona(
        name="Young professional, Berlin",
        salary=2850.00,
        employer="Arbeitgeber GmbH",
        fixed={"Housing": ("Hausverwaltung Miete", 890.00, 1), "Utilities": ("Stadtwerke", 64.00, 15)},
        subscriptions=(("Netflix", 13.99, 3), ("Spotify", 10.99, 10), ("Telekom Mobil", 24.95, 20)),
        variable={
            "Groceries": Variable(("REWE", "Lidl", "Edeka", "Aldi"), 8, 36.0, 0.35),
            "Restaurant": Variable(("L'Osteria", "Vapiano", "Dominos", "Burgermeister"), 3, 27.0, 0.7),
            "Transport": Variable(("Uber", "Bolt", "DB Fernverkehr"), 2, 18.0, 0.5),
            "Shopping": Variable(("Zalando", "Amazon", "dm", "IKEA"), 2, 38.0, 0.5),
            "Entertainment": Variable(("Kino Zoo Palast", "Eventim"), 1, 24.0, 0.8),
        },
    ),
    "family": Persona(
        name="Family of four, Munich",
        salary=5400.00,
        employer="Maschinenbau AG",
        fixed={"Housing": ("Wohnbau Miete", 1780.00, 1), "Utilities": ("SWM Energie", 142.00, 15)},
        subscriptions=(("Disney+", 9.99, 5), ("Vodafone Kabel", 39.99, 12), ("Kita Beitrag", 180.00, 3)),
        variable={
            "Groceries": Variable(("Edeka", "Aldi", "Kaufland", "dm"), 12, 58.0, 0.4),
            "Restaurant": Variable(("Hans im Glück", "Pizzeria Roma", "McDonald's"), 2, 46.0, 0.75),
            "Transport": Variable(("Aral", "Shell", "MVG"), 4, 52.0, 0.4),
            "Shopping": Variable(("Amazon", "H&M Kids", "Decathlon", "IKEA"), 3, 55.0, 0.5),
            "Health": Variable(("Apotheke am Markt", "Zahnarzt Dr. Weber"), 1, 32.0, 0.1),
        },
    ),
    "student": Persona(
        name="Student, Hamburg",
        salary=1100.00,
        employer="Studierendenwerk Nebenjob",
        fixed={"Housing": ("WG Miete", 480.00, 1)},
        subscriptions=(("Spotify Student", 5.99, 8), ("Deutschlandticket", 49.00, 1)),
        variable={
            "Groceries": Variable(("Lidl", "Aldi", "Netto"), 7, 21.0, 0.4),
            "Restaurant": Variable(("Mensa", "Dönerladen", "Vapiano"), 5, 9.5, 0.45),
            "Shopping": Variable(("Amazon", "Thalia", "Primark"), 1, 26.0, 0.5),
            "Entertainment": Variable(("Uebel & Gefährlich", "Kino"), 2, 15.0, 0.85),
        },
    ),
}


def _random_day(rng: np.random.Generator, month: pd.Period, weekend: bool) -> pd.Timestamp:
    days = pd.date_range(month.start_time, month.end_time.normalize(), freq="D")
    pool = [d for d in days if (d.dayofweek >= 5) == weekend] or list(days)
    return pool[rng.integers(len(pool))]


def generate_transactions(
    persona_key: str,
    seed: int = 0,
    months: int = 12,
    end_month: str = "2026-08",
    spike_probability: float = 0.25,
    unusual_probability: float = 0.2,
) -> pd.DataFrame:
    persona = PERSONAS[persona_key]
    rng = np.random.default_rng(seed)
    periods = pd.period_range(end=pd.Period(end_month, freq="M"), periods=months, freq="M")
    rows: list[tuple] = []

    for month in periods:
        start = month.start_time

        rows.append((month.end_time.normalize() - pd.Timedelta(days=1), persona.employer, "Income", persona.salary))
        for category, (merchant, amount, day) in persona.fixed.items():
            rows.append((start + pd.Timedelta(days=day - 1), merchant, category, amount))
        for merchant, amount, day in persona.subscriptions:
            rows.append((start + pd.Timedelta(days=day - 1), merchant, "Subscriptions", amount))

        # A spike makes one category unusually busy this month (e.g. a holiday, a birthday).
        spike = rng.choice(list(persona.variable)) if rng.random() < spike_probability else None

        for category, spec in persona.variable.items():
            visits = rng.poisson(spec.visits_per_month * (2.5 if category == spike else 1.0))
            for _ in range(visits):
                weekend = rng.random() < spec.weekend_bias
                amount = rng.lognormal(np.log(spec.typical_amount), 0.3)
                merchant = spec.merchants[rng.integers(len(spec.merchants))]
                rows.append((_random_day(rng, month, weekend), merchant, category, round(float(amount), 2)))

        # A one-off payment far above what the merchant usually charges.
        if rng.random() < unusual_probability:
            category = rng.choice(list(persona.variable))
            spec = persona.variable[category]
            merchant = spec.merchants[0]
            amount = spec.typical_amount * rng.uniform(3, 6)
            rows.append((_random_day(rng, month, rng.random() < 0.5), merchant, category, round(float(amount), 2)))

    df = pd.DataFrame(rows, columns=["date", "merchant", "category", "amount"])
    return df.sort_values("date").reset_index(drop=True)


if __name__ == "__main__":
    import sys

    key = sys.argv[1] if len(sys.argv) > 1 else "young_professional"
    frame = generate_transactions(key, seed=int(sys.argv[2]) if len(sys.argv) > 2 else 0)
    print(frame.to_csv(index=False, date_format="%Y-%m-%d"), end="")
