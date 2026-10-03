jest.mock("axios");
jest.mock("../src/ticketClient");

const axios = require("axios");
const { createTicket } = require("../src/ticketClient");
const { intakeTicket, formatConfirmation } = require("../src/orchestratorClient");

const payload = { title: "Login broken", description: "Login broken on Safari", reportedBy: "U1", channel: "C1" };
const ticket = { ticket_id: "APM-12", title: "Login broken" };

beforeEach(() => jest.resetAllMocks());

test("routes intake through the orchestrator and picks out this ticket's priority", async () => {
  axios.post.mockResolvedValue({ data: {
    created_ticket: ticket,
    errors: [],
    duplicates: [{ ticket_id: "APM-1", title: "Login page crashes on Safari", score: 0.82, status: "Open" }],
    priority_report: { tickets: [
      { ticket_id: "APM-3", assigned_priority: "Low", priority_score: 10 },
      { ticket_id: "APM-12", assigned_priority: "High", priority_score: 82, reasoning: "Blocks sign-in." },
    ] },
    agent_session: { branch_created: true, branch: "apm/APM-12-login-broken" },
  } });

  const result = await intakeTicket(payload);

  const [url, body] = axios.post.mock.calls[0];
  expect(url).toMatch(/\/orchestrate\/start$/);
  expect(body.trigger).toBe("slack_message");
  expect(body.slack_payload).toMatchObject({ title: "Login broken", reported_by: "U1", channel: "C1" });
  expect(result.via).toBe("orchestrator");
  expect(result.priority.assigned_priority).toBe("High");
  expect(result.duplicates).toHaveLength(1);
  expect(createTicket).not.toHaveBeenCalled();
});

test("falls back to the Ticket Service when the orchestrator is unreachable", async () => {
  axios.post.mockRejectedValue(Object.assign(new Error("connect ECONNREFUSED"), { code: "ECONNREFUSED" }));
  createTicket.mockResolvedValue(ticket);

  const result = await intakeTicket(payload);

  expect(createTicket).toHaveBeenCalledWith(payload);
  expect(result).toEqual({ ticket, priority: null, via: "direct", duplicates: [], agentSession: null });
});

test("does not retry when the orchestrator may already have created the ticket", async () => {
  // A timeout or 500 means the workflow may have run – retrying could duplicate the ticket.
  axios.post.mockRejectedValue(Object.assign(new Error("timeout"), { code: "ECONNABORTED" }));
  await expect(intakeTicket(payload)).rejects.toThrow("timeout");

  axios.post.mockRejectedValue(Object.assign(new Error("boom"), { response: { status: 500 } }));
  await expect(intakeTicket(payload)).rejects.toThrow("boom");

  expect(createTicket).not.toHaveBeenCalled();
});

test("creates the ticket directly when the workflow ran but ticket creation failed", async () => {
  axios.post.mockResolvedValue({ data: { created_ticket: null, errors: ["create_ticket_node failed"] } });
  createTicket.mockResolvedValue(ticket);
  const result = await intakeTicket(payload);
  expect(result.via).toBe("direct");
});

test("formats the Slack confirmation with priority, duplicates and agent session", () => {
  const text = formatConfirmation({
    ticket,
    priority: { assigned_priority: "High", priority_score: 82, reasoning: "Blocks sign-in." },
    duplicates: [{ ticket_id: "APM-1", title: "Login page crashes on Safari", score: 0.824, status: "Open" }],
    agentSession: { branch_created: true, branch: "apm/APM-12-login-broken" },
  });
  expect(text).toContain("✅ Ticket created: *APM-12* – Login broken");
  expect(text).toContain("AI priority: *High* (82/100)");
  expect(text).toContain("> Blocks sign-in.");
  expect(text).toContain("*APM-1* – Login page crashes on Safari (82% similar, Open)");
  expect(text).toContain("branch `apm/APM-12-login-broken`");
});

test("keeps the confirmation minimal when nothing extra is known", () => {
  expect(formatConfirmation({ ticket })).toBe("✅ Ticket created: *APM-12* – Login broken");
});
