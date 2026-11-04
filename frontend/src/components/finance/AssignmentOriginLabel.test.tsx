import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { AssignmentOriginLabel } from "./AssignmentOriginLabel";
it("distinguishes a human-approved AI proposal from manual and approved-rule origins", () => {
  render(
    <AssignmentOriginLabel
      origin={{
        origin: "approved_llm",
        version: 1,
        proposal_item_id: "proposal",
        display_description: "Opis",
        target_path: "Dom",
      }}
    />,
  );
  expect(
    screen.getByText("Kategoria z propozycji AI — zatwierdzona przez Ciebie"),
  ).toBeInTheDocument();
});
