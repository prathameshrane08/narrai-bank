"""White-label configuration: one JSON file per bank in this folder.

A bank chooses its display name, assistant name, logo, colours and legal
footer. Colours are validated for WCAG AA contrast when loaded, so a bank
cannot ship a theme its own customers can't read.

The tenant is selected per request with the X-NarrAI-Tenant header.
"""

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

TENANT_DIR = Path(__file__).parent
DEFAULT_TENANT = "narrai"
HEX_COLOUR = r"^#[0-9a-fA-F]{6}$"
MIN_CONTRAST = 4.5  # WCAG AA for normal text


def _luminance(hex_colour: str) -> float:
    channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(a: str, b: str) -> float:
    lighter, darker = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


class Colours(BaseModel):
    brand: str = Field(pattern=HEX_COLOUR, description="Header, buttons, links")
    brand_dark: str = Field(pattern=HEX_COLOUR, description="Account panel, hover states")
    brand_soft: str = Field(pattern=HEX_COLOUR, description="Tinted badges and highlights")
    on_brand: str = Field("#ffffff", pattern=HEX_COLOUR, description="Text on brand surfaces")

    @model_validator(mode="after")
    def readable(self):
        checks = {
            "on_brand on brand": contrast_ratio(self.on_brand, self.brand),
            "on_brand on brand_dark": contrast_ratio(self.on_brand, self.brand_dark),
            "brand on white (links)": contrast_ratio(self.brand, "#ffffff"),
            "brand on brand_soft (badges)": contrast_ratio(self.brand, self.brand_soft),
        }
        failing = {name: round(ratio, 2) for name, ratio in checks.items() if ratio < MIN_CONTRAST}
        if failing:
            raise ValueError(f"colours fail WCAG AA contrast {MIN_CONTRAST}:1 — {failing}")
        return self


class Tenant(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]{2,40}$")
    bank_name: str = Field(min_length=2, max_length=60)
    assistant_name: str = Field(min_length=2, max_length=40)
    tagline: str = Field(max_length=120)
    logo: str = Field(description="Path under the frontend's public folder, e.g. /tenants/narrai.svg")
    colours: Colours
    account_label: str = "Current account"
    legal_footer: str = Field(max_length=400)
    advice_contact: str = Field(description="Where customers are sent for regulated advice")
    features: dict[str, bool] = Field(default_factory=lambda: {"story": True, "chat": True, "insights": True})

    @field_validator("logo")
    @classmethod
    def local_logo(cls, value: str) -> str:
        if not value.startswith("/tenants/") or ".." in value:
            raise ValueError("logo must be a file under /tenants/")
        return value


@lru_cache
def load_tenants() -> dict[str, Tenant]:
    tenants = {}
    for path in sorted(TENANT_DIR.glob("*.json")):
        tenant = Tenant.model_validate(json.loads(path.read_text()))
        if tenant.id != path.stem:
            raise ValueError(f"{path.name}: id '{tenant.id}' must match the file name")
        tenants[tenant.id] = tenant
    if DEFAULT_TENANT not in tenants:
        raise ValueError(f"missing default tenant '{DEFAULT_TENANT}.json'")
    return tenants


def get_tenant(tenant_id: str | None) -> Tenant | None:
    return load_tenants().get(tenant_id or DEFAULT_TENANT)
