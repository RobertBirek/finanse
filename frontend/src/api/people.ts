import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { AxiosError } from "axios";
import api from "../lib/api";
import { useAuthStore } from "../stores/authStore";
import type { Transaction } from "./finance";

export interface Person {
  id: string;
  name: string;
  is_active: boolean;
  version: number;
  reference_account_id: string | null;
}
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
export interface PersonSummary {
  person_id: string;
  gift_count: number;
  received_gifts_pln: number;
  received_by_currency: Record<string, number>;
}
export interface PersonLinkContext {
  transaction_id: string;
  snapshot: string;
  person: Person | null;
  eligible: boolean;
  reason: string | null;
}
export interface PersonInput {
  name: string;
  reference_account_id: string | null;
}
export interface PersonUpdate extends Partial<PersonInput> {
  id: string;
  expected_version: number;
  is_active?: boolean;
}
interface GiftInput {
  id: string;
  key: string;
  expected_transaction_snapshot: string;
}

function usePersonQuery<T>(
  key: unknown[],
  path: string,
  params?: object,
  enabled = true,
) {
  const session = useAuthStore((s) => s.sessionVersion);
  const user = useAuthStore((s) => s.user);
  return useQuery<T>({
    queryKey: ["finance", "people", session, ...key],
    enabled: !!user && enabled,
    queryFn: async ({ signal }) =>
      (await api.get<T>(path, { params, signal })).data,
  });
}
export function usePeople(
  params: {
    include_archived?: boolean;
    reference_account_id?: string;
    offset?: number;
  } = {},
  enabled = true,
) {
  return usePersonQuery<Page<Person>>(
    ["list", params],
    "/finance/people",
    { limit: 50, ...params },
    enabled,
  );
}
export function usePerson(id: string) {
  return usePersonQuery<Person>(
    ["detail", id],
    `/finance/people/${id}`,
    undefined,
    !!id,
  );
}
export function usePersonSummary(id: string) {
  return usePersonQuery<PersonSummary>(
    ["summary", id],
    `/finance/people/${id}/summary`,
    undefined,
    !!id,
  );
}
export function usePersonGifts(id: string, offset = 0) {
  return usePersonQuery<Page<Transaction>>(
    ["gifts", id, offset],
    `/finance/people/${id}/gifts`,
    { limit: 50, offset },
    !!id,
  );
}
export function usePersonLinkContext(id: string) {
  return usePersonQuery<PersonLinkContext>(
    ["link", id],
    `/finance/transactions/${id}/person-link`,
    undefined,
    !!id,
  );
}
function usePeopleWrite<Input, Output>(
  write: (input: Input) => Promise<Output>,
) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: write,
    retry: false,
    onMutate: () => ({ session: useAuthStore.getState().sessionVersion }),
    onSuccess: (_result, _input, ctx) => {
      if (ctx?.session === useAuthStore.getState().sessionVersion)
        client.invalidateQueries({ queryKey: ["finance", "people"] });
    },
  });
}
export function useCreatePerson() {
  return usePeopleWrite<PersonInput, Person>(
    async (input) => (await api.post<Person>("/finance/people", input)).data,
  );
}
export function useUpdatePerson() {
  return usePeopleWrite<PersonUpdate, Person>(
    async ({ id, ...input }) =>
      (await api.patch<Person>(`/finance/people/${id}`, input)).data,
  );
}
export function useLinkGift() {
  return usePeopleWrite<GiftInput & { person_id: string }, PersonLinkContext>(
    async ({ id, key, ...input }) =>
      (
        await api.put<PersonLinkContext>(
          `/finance/transactions/${id}/person-link`,
          input,
          { headers: { "Idempotency-Key": key } },
        )
      ).data,
  );
}
export function useUnlinkGift() {
  return usePeopleWrite<GiftInput, PersonLinkContext>(
    async ({ id, key, ...input }) =>
      (
        await api.delete<PersonLinkContext>(
          `/finance/transactions/${id}/person-link`,
          { data: input, headers: { "Idempotency-Key": key } },
        )
      ).data,
  );
}
export function personError(error: unknown) {
  const detail = (error as AxiosError<{ detail?: unknown }>)?.response?.data
    ?.detail;
  return typeof detail === "string"
    ? detail
    : "Nie udało się zapisać danych. Sprawdź połączenie i odśwież dane przed kolejną zmianą.";
}
