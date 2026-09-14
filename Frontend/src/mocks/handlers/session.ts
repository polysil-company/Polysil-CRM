import { http, HttpResponse } from "msw";

import { buildApiUrl } from "@/lib/api/url";
import { readMockRole } from "@/lib/dev/mock-settings";
import { mockSessionFor } from "@/mocks/data/sessions";

import { applyScenario } from "./scenario";

export const sessionHandlers = [
  http.get(buildApiUrl("/me"), async () => {
    // The shell needs the session to show the scenario switcher, so it never fails.
    await applyScenario({ allowFailure: false });
    return HttpResponse.json(mockSessionFor(readMockRole()));
  }),
];
