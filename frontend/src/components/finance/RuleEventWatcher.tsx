import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useRuleEvents } from "../../api/categorizationRules";
import { invalidateFinanceLedger } from "../../api/finance";
import { useAuthStore } from "../../stores/authStore";

export function RuleEventWatcher() {
  const query = useRuleEvents();
  const client = useQueryClient();
  const stamp = query.dataUpdatedAt;
  const session = query.data?.session;
  useEffect(() => {
    if (stamp && session === useAuthStore.getState().sessionVersion) {
      invalidateFinanceLedger(client);
      client.invalidateQueries({ queryKey: ["finance", "categorization"] });
    }
  }, [stamp, session, client]);
  return null;
}
