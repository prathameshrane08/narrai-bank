import type { Tenant } from "./api";

/** Apply a bank's white-label colours by overriding the brand CSS variables. */
export function applyTenantTheme(tenant: Tenant) {
  const root = document.documentElement.style;
  root.setProperty("--brand", tenant.colours.brand);
  root.setProperty("--accent", tenant.colours.brand);
  root.setProperty("--brand-dark", tenant.colours.brand_dark);
  root.setProperty("--brand-soft", tenant.colours.brand_soft);
  root.setProperty("--on-brand", tenant.colours.on_brand);
  document.title = tenant.bank_name;
}

/** The tenant requested in the URL (?bank=kestrel), used by the pitch demo's brand switcher. */
export function tenantFromUrl(): string | null {
  const id = new URLSearchParams(window.location.search).get("bank");
  return id && /^[a-z0-9-]{2,40}$/.test(id) ? id : null;
}
