import { delay, HttpResponse } from "msw";

import { readMockScenario, type MockScenario } from "@/lib/dev/mock-settings";

export interface ScenarioOutcome {
  readonly scenario: MockScenario;
  /** Set when the scenario replaces the normal response (e.g. a 500). */
  readonly failure: Response | null;
}

export interface ScenarioOptions {
  /**
   * False for endpoints the app shell needs (e.g. GET /me): they keep working in
   * the "error" scenario so the menu that switches scenarios stays usable.
   */
  readonly allowFailure?: boolean;
}

/**
 * Applies the developer-selected mock scenario: realistic latency (instant in
 * Node tests), a slow network, or a server error. "empty" and "contract" are
 * applied by each handler because they depend on the response shape.
 */
export async function applyScenario(options: ScenarioOptions = {}): Promise<ScenarioOutcome> {
  const { allowFailure = true } = options;
  const scenario = readMockScenario();
  await delay(scenario === "slow" ? 3000 : "real");

  if (scenario === "error" && allowFailure) {
    return {
      scenario,
      failure: HttpResponse.json(
        {
          error: { code: "MOCK_SERVER_ERROR", message: "Simulated server error (mock scenario)." },
        },
        { status: 500 },
      ),
    };
  }

  return { scenario, failure: null };
}
