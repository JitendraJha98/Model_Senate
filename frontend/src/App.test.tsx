import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import App from "./App";
import { expect, test, vi } from "vitest";

vi.mock("./api", () => ({
  getConfig: async () => ({
    models: [
      { id: "a", provider: "openrouter", model: "a", display_name: "A", enabled: true, supports_streaming: true, missing_key: false },
      { id: "b", provider: "openrouter", model: "b", display_name: "B", enabled: true, supports_streaming: true, missing_key: true },
      { id: "c", provider: "openrouter", model: "c", display_name: "C", enabled: true, supports_streaming: true, missing_key: false }
    ],
    defaults: { selected_model_ids: ["a", "b", "c"], leader_model_id: "a", min_models: 3 }
  }),
  getConversations: async () => [],
  runSenate: async () => {
    throw new Error("not used in this test");
  }
}));

test("renders model selection requirement", async () => {
  render(<App />);
  expect(await screen.findByText(/Select at least 3 models/i)).toBeInTheDocument();
});
