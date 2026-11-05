import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it, vi } from "vitest";
import api from "../../../lib/api";
import { ReceiptReadEvidence } from "./ReceiptReadEvidence";
import { readResult } from "./receiptReadTestData";
it("shows immutable source text and keeps review checkboxes controlled by the current body", async () => {
  vi.spyOn(api, "get").mockResolvedValue({
    data: {
      ...readResult,
      proposal: {
        ...readResult.proposal,
        problems: [
          {
            key: "source/missing_rows",
            code: "missing_rows",
            message: "Sprawdź brakujące produkty.",
            requires_ack: true,
          },
        ],
      },
    },
  });
  const evidence = {
    extraction_id: "e",
    extraction_sha256: "h",
    job_id: "job",
    source_document_id: "photo",
    source_sha256: "h",
    line_map: {
      a: {
        source_index: 0,
        source_text: "MLEKO 80,00",
        original_field_sha256: {},
        edited_fields: ["amount_minor"],
      },
    },
    discount_map: {},
    pending_problems: [
      {
        key: "source/missing_rows",
        code: "missing_rows",
        line_index: null,
        discount_index: null,
        message: "Sprawdź brakujące produkty.",
        requires_ack: true,
      },
    ],
    acknowledgements: {},
  };
  const onChange = vi.fn();
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <ReceiptReadEvidence
        billId="bill"
        evidence={evidence}
        selected={[]}
        disabled={false}
        onChange={onChange}
      />
    </QueryClientProvider>,
  );
  expect(await screen.findByText("MLEKO 80,00")).toBeInTheDocument();
  expect(screen.getByText(/Zmieniono: kwota/)).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText(/Sprawdzono: Sprawdź brakujące/));
  expect(onChange).toHaveBeenCalledWith(["source/missing_rows"]);
  view.rerender(
    <QueryClientProvider client={client}>
      <ReceiptReadEvidence
        billId="bill"
        evidence={evidence}
        selected={[]}
        disabled={false}
        onChange={onChange}
      />
    </QueryClientProvider>,
  );
  expect(screen.getByRole("checkbox")).not.toBeChecked();
});
