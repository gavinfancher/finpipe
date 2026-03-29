import { isManaged } from "./edition";

const MANAGED_ONLY = new Set([
  "teams",
  "sso",
  "rbac",
  "audit_log",
  "admin",
  "usage_analytics",
  "managed_ingestion",
  "hosted_models",
]);

export function featureEnabled(feature: string): boolean {
  if (MANAGED_ONLY.has(feature)) return isManaged;
  return true;
}
