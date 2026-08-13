import { describe, expect, it } from "vitest";
import {
  getMessagesRefetchInterval,
  hasPendingConfirmation,
  type Message,
} from "./advisor";

const message = (status: string): Message => ({
  id: "message-1",
  conversation_id: "conversation-1",
  role: "assistant",
  content: "",
  tool_executions: [
    {
      id: "execution-1",
      tool_name: "create_task",
      arguments: null,
      result: null,
      status,
    },
  ],
  created_at: "2026-08-12T12:00:00Z",
});

describe("hasPendingConfirmation", () => {
  it("returns false when there are no messages", () => {
    expect(hasPendingConfirmation(undefined)).toBe(false);
    expect(hasPendingConfirmation([])).toBe(false);
  });

  it("returns true when any tool execution needs confirmation", () => {
    expect(
      hasPendingConfirmation([
        message("completed"),
        message("pending_confirmation"),
      ]),
    ).toBe(true);
  });

  it("returns false when all tool executions are resolved", () => {
    expect(
      hasPendingConfirmation([message("completed"), message("denied")]),
    ).toBe(false);
  });

  it("polls every two seconds only while confirmation is pending", () => {
    expect(getMessagesRefetchInterval([message("pending_confirmation")])).toBe(
      2000,
    );
    expect(getMessagesRefetchInterval([message("completed")])).toBe(false);
    expect(getMessagesRefetchInterval(undefined)).toBe(false);
  });
});
