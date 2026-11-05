/** Tab-scoped recovery metadata only: IDs, hashes, versions and a command key, never image bytes. */
import { useAuthStore } from "../../../stores/authStore";
import type { ReadRequest } from "../../../api/receiptRead";

export type ReceiptReadIntent = {
  action: "start" | "cancel" | "import";
  input: ReadRequest;
};
const prefix = "personal-advisor.receipt-read.intent.v1:";
const boot = crypto.randomUUID();
interface StoredIntent {
  version: 1;
  owner: string;
  boot: string;
  session: number;
  billId: string;
  photo: string;
  jobId: string | null;
  intent: ReceiptReadIntent;
}
function storageKey(owner: string, billId: string) {
  return prefix + encodeURIComponent(owner) + ":" + encodeURIComponent(billId);
}
function text(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= 200;
}
function object(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}
function valid(value: unknown): value is StoredIntent {
  if (
    !object(value) ||
    value.version !== 1 ||
    !text(value.owner) ||
    !text(value.boot) ||
    !text(value.billId) ||
    !Number.isSafeInteger(value.session) ||
    typeof value.photo !== "string" ||
    (value.jobId !== null && !text(value.jobId)) ||
    !object(value.intent)
  )
    return false;
  const intent = value.intent,
    input = intent.input;
  if (
    !["start", "cancel", "import"].includes(String(intent.action)) ||
    !object(input) ||
    input.billId !== value.billId ||
    input.session !== value.session ||
    !text(input.key) ||
    !object(input.body)
  )
    return false;
  const b = input.body;
  const hash = (s: unknown) =>
    typeof s === "string" && /^[a-f0-9]{64}$/.test(s);
  const integer = (n: unknown) =>
    typeof n === "number" && Number.isSafeInteger(n) && n >= 0;
  const allowed =
    intent.action === "start"
      ? [
          "document_id",
          "reread_of_job_id",
          "expected_export_snapshot",
          "confirmed",
        ]
      : intent.action === "cancel"
        ? ["expected_version"]
        : [
            "job_id",
            "expected_state_version",
            "expected_import_snapshot",
            "confirmed_replace",
          ];
  if (Object.keys(b).some((k) => !allowed.includes(k))) return false;
  if (intent.action === "start")
    return (
      text(b.document_id) &&
      (b.reread_of_job_id === null || text(b.reread_of_job_id)) &&
      hash(b.expected_export_snapshot) &&
      b.confirmed === true
    );
  if (intent.action === "cancel")
    return text(input.jobId) && integer(b.expected_version);
  return (
    text(b.job_id) &&
    integer(b.expected_state_version) &&
    hash(b.expected_import_snapshot) &&
    b.confirmed_replace === true
  );
}
export function loadReceiptReadIntent(
  owner: string | null,
  billId: string,
  session: number,
): StoredIntent | null {
  if (!owner) return null;
  try {
    const key = storageKey(owner, billId),
      raw = sessionStorage.getItem(key);
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    if (
      !valid(value) ||
      value.owner !== owner ||
      value.billId !== billId ||
      (value.boot === boot && value.session !== session)
    ) {
      sessionStorage.removeItem(key);
      return null;
    }
    // The in-memory counter resets on a page reload. Only a new runtime with the
    // same authenticated owner may rebase it, and recovery still requires a click.
    return {
      ...value,
      boot,
      session,
      intent: { ...value.intent, input: { ...value.intent.input, session } },
    };
  } catch {
    return null;
  }
}
export function persistReceiptReadIntent(
  owner: string | null,
  billId: string,
  session: number,
  intent: ReceiptReadIntent,
  photo: string,
  jobId: string | null,
): boolean {
  if (!owner) return false;
  try {
    const value: StoredIntent = {
      version: 1,
      owner,
      boot,
      session,
      billId,
      photo,
      jobId,
      intent,
    };
    if (!valid(value)) return false;
    sessionStorage.setItem(storageKey(owner, billId), JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}
export function clearReceiptReadIntent(owner: string | null, billId: string) {
  try {
    if (owner) sessionStorage.removeItem(storageKey(owner, billId));
  } catch {
    /* Memory intent remains usable when storage becomes unavailable. */
  }
}
function purge(keepOwner: string | null = null) {
  try {
    for (const key of Object.keys(sessionStorage)) {
      if (!key.startsWith(prefix)) continue;
      const raw = sessionStorage.getItem(key);
      let keep = false;
      try {
        keep = !!keepOwner && !!raw && JSON.parse(raw).owner === keepOwner;
      } catch {
        /* Invalid metadata is never recovered. */
      }
      if (!keep) sessionStorage.removeItem(key);
    }
  } catch {
    /* No readable browser persistence. */
  }
}
useAuthStore.subscribe((next, previous) => {
  const initialAuthentication =
    previous.authStatus === "loading" &&
    !previous.user &&
    next.authStatus === "authenticated";
  if (initialAuthentication) {
    purge(next.user?.id ?? null);
    return;
  }
  if (
    next.sessionVersion !== previous.sessionVersion ||
    next.user?.id !== previous.user?.id ||
    next.authStatus === "unauthenticated"
  )
    purge();
});
