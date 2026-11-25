import { useAuthStore } from "../../stores/authStore";
import { RuleEventWatcher } from "./RuleEventWatcher";
import { SuggestionActivityWatcher } from "./SuggestionActivityWatcher";

export function FinanceActivityMonitor() {
  const authenticated = useAuthStore(
    (state) => state.authStatus === "authenticated" && !!state.user,
  );
  if (!authenticated) return null;
  return (
    <>
      <RuleEventWatcher />
      <SuggestionActivityWatcher />
    </>
  );
}
