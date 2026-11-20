import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  invalidateProposals,
  useSuggestionActivity,
} from "../../api/categoryProposals";
import { useAuthStore } from "../../stores/authStore";

export function SuggestionActivityWatcher() {
  const query = useSuggestionActivity();
  const client = useQueryClient();
  const session = query.data?.session;
  const outcomes = query.data?.recent_outcomes
    .map(({ id, state, result_kind }) =>
      JSON.stringify([id, state, result_kind]),
    )
    .sort()
    .join(",");
  const previous = useRef<{ session: number; outcomes: string } | null>(null);
  useEffect(() => {
    if (
      outcomes === undefined ||
      session !== useAuthStore.getState().sessionVersion
    )
      return;
    const last = previous.current;
    if (last?.session === session ? last.outcomes !== outcomes : !!outcomes)
      invalidateProposals(client);
    previous.current = { session, outcomes };
  }, [outcomes, session, client]);
  return null;
}
