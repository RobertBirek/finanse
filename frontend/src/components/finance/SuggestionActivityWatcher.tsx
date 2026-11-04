import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  invalidateProposals,
  useSuggestionActivity,
} from "../../api/categoryProposals";
import { useAuthStore } from "../../stores/authStore";

export function SuggestionActivityWatcher() {
  const query = useSuggestionActivity();
  const client = useQueryClient();
  const stamp = query.dataUpdatedAt,
    session = query.data?.session;
  useEffect(() => {
    if (stamp && session === useAuthStore.getState().sessionVersion)
      invalidateProposals(client);
  }, [stamp, session, client]);
  return null;
}
