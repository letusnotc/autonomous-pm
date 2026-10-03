process.env.JIRA_PROJECT_KEYS = "APM";
const { extractTicketIds } = require("../src/ticketExtractor");

test("finds APM ticket IDs in commit messages and branch names", () => {
  expect(extractTicketIds("APM-15: send Gemini key in header")).toEqual(["APM-15"]);
  expect(extractTicketIds("Merge branch apm/APM-7-standup-digest into main")).toEqual(["APM-7"]);
});

test("is case-insensitive and de-duplicates", () => {
  expect(extractTicketIds("apm-3 and APM-3 and Apm-4")).toEqual(["APM-3", "APM-4"]);
});

test("understands closes #N and [TICKET:...] tags", () => {
  expect(extractTicketIds("Fixes #42")).toEqual(["#42"]);
  expect(extractTicketIds("[TICKET:APM-5] tidy up")).toContain("APM-5");
});

test("ignores text without ticket references", () => {
  expect(extractTicketIds("Refactor logging")).toEqual([]);
  expect(extractTicketIds("")).toEqual([]);
  expect(extractTicketIds(null)).toEqual([]);
});
