import { useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAuthStore } from "../stores/authStore";

export function SessionQueryProvider({ children }: { children: ReactNode }) {
  const sessionVersion = useAuthStore((state) => state.sessionVersion);
  // A new subtree owns a new client. Old query/mutation completions can only
  // touch their old client, including logout/re-login as the same owner.
  return <QuerySession key={sessionVersion}>{children}</QuerySession>;
}

function QuerySession({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false },
        },
      }),
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
