/**
 * orchestratorClient.js
 * Routes Slack intake through the Orchestrator's `slack_message` workflow
 * (create ticket → prioritise). Falls back to creating the ticket directly
 * in the Ticket Service when the orchestrator can't be reached.
 */
const axios = require("axios");
const { createTicket } = require("./ticketClient");

const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_URL || "http://localhost:3005";
// Prioritisation calls an LLM over every open ticket, so allow plenty of time.
const ORCHESTRATOR_TIMEOUT_MS = Number(process.env.ORCHESTRATOR_TIMEOUT_MS || 180000);

const UNREACHABLE_CODES = new Set(["ECONNREFUSED", "ENOTFOUND", "EAI_AGAIN", "EHOSTUNREACH"]);

// Only fall back when we know the orchestrator never ran the workflow –
// otherwise a retry could create a duplicate ticket.
function orchestratorNotReached(err) {
  if (!err.response) return UNREACHABLE_CODES.has(err.code);
  return [404, 502, 503].includes(err.response.status);
}

/**
 * @returns {Promise<{ ticket: object, priority: object|null, via: "orchestrator"|"direct" }>}
 */
async function intakeTicket(payload) {
  try {
    const { data } = await axios.post(`${ORCHESTRATOR_URL}/orchestrate/start`, {
      trigger: "slack_message",
      post_standup_to_slack: false,
      slack_payload: {
        title:            payload.title,
        description:      payload.description,
        ticket_type:      payload.ticketType || "task",
        priority:         payload.priority   || "Medium",
        reported_by:      payload.reportedBy,
        source:           payload.source     || "slack",
        channel:          payload.channel,
        slack_message_ts: payload.slackMessageTs,
      },
    }, {
      headers: { "Content-Type": "application/json" },
      timeout: ORCHESTRATOR_TIMEOUT_MS,
    });

    if (data.errors?.length) console.warn("[intake] Orchestrator reported:", data.errors.join(" | "));

    if (data.created_ticket) {
      const id = data.created_ticket.ticket_id;
      const priority = data.priority_report?.tickets?.find(t => t.ticket_id === id) || null;
      return { ticket: data.created_ticket, priority, via: "orchestrator" };
    }
    // Workflow ran but ticket creation failed – try the Ticket Service directly.
  } catch (err) {
    if (!orchestratorNotReached(err)) throw err;
    console.warn(`[intake] Orchestrator unreachable (${err.code || err.response?.status}); creating ticket directly`);
  }

  const ticket = await createTicket(payload);
  return { ticket, priority: null, via: "direct" };
}

/** Slack mrkdwn confirmation, including the AI priority when available. */
function formatConfirmation({ ticket, priority }) {
  let text = `✅ Ticket created: *${ticket.ticket_id}* – ${ticket.title}`;
  if (priority) {
    text += `\n:bar_chart: AI priority: *${priority.assigned_priority}* (${priority.priority_score}/100)`;
    if (priority.reasoning) text += `\n> ${priority.reasoning}`;
  }
  return text;
}

module.exports = { intakeTicket, formatConfirmation };
