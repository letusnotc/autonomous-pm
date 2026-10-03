require("dotenv").config();
const { App, ExpressReceiver } = require("@slack/bolt");
const { parseTicketFromMessage } = require("./parser");
const { intakeTicket, formatConfirmation } = require("./orchestratorClient");

const receiver = new ExpressReceiver({
  signingSecret: process.env.SLACK_SIGNING_SECRET || "dev-secret",
  endpoints: "/slack/events",
});

const app = new App({
  token: process.env.SLACK_BOT_TOKEN,
  receiver,
});

receiver.router.get("/health", (req, res) => {
  res.json({ status: "ok", service: "slack-intake-service", port: process.env.PORT || 3006 });
});

app.message(async ({ message, client }) => {
  try {
    if (message.subtype || message.bot_id) return;
    const ticketData = parseTicketFromMessage(message);
    if (!ticketData) return;

    console.log(`[intake] Ticket trigger from ${message.user}: ${ticketData.title}`);
    const result = await intakeTicket({
      title:          ticketData.title,
      description:    ticketData.description,
      reportedBy:     message.user,
      source:         "slack",
      channel:        message.channel,
      slackMessageTs: message.ts,
    });

    await client.chat.postMessage({
      channel:   message.channel,
      thread_ts: message.ts,
      text:      formatConfirmation(result),
    });
    console.log(`[intake] Ticket ${result.ticket.ticket_id} created via ${result.via}`);
  } catch (err) {
    console.error("[intake] Error:", err.message);
  }
});

app.command("/ticket", async ({ command, ack, respond }) => {
  await ack();
  try {
    const text = command.text?.trim();
    if (!text) { await respond("Usage: `/ticket <description>`"); return; }

    const result = await intakeTicket({
      title:       text.split("\n")[0].slice(0, 200),
      description: text,
      reportedBy:  command.user_id,
      source:      "slack-command",
      channel:     command.channel_id,
    });

    await respond({
      text:          formatConfirmation(result),
      response_type: "in_channel",
    });
    console.log(`[intake] Ticket ${result.ticket.ticket_id} created via ${result.via}`);
  } catch (err) {
    console.error("[intake] Command error:", err.message);
    await respond("❌ Failed to create ticket. Please try again.");
  }
});

const PORT = process.env.PORT || 3006;
(async () => {
  await app.start(PORT);
  console.log(`⚡ Slack Intake Service running on port ${PORT}`);
})();
