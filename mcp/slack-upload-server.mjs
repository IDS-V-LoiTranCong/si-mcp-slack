import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import * as z from "zod/v4";

const MAX_MARKDOWN_BYTES = 1024 * 1024;
const CHANNEL_ID_PATTERN = /^[CG][A-Z0-9]+$/;
const THREAD_TS_PATTERN = /^\d+\.\d+$/;

const server = new McpServer({
  name: "slack-upload",
  version: "1.0.0",
});

function getSlackToken() {
  const token = process.env.SLACK_USER_TOKEN;

  if (!token) {
    throw new Error("SLACK_USER_TOKEN is not configured");
  }

  if (!token.startsWith("xoxp-")) {
    throw new Error("SLACK_USER_TOKEN must be a Slack User OAuth token (xoxp-...)");
  }

  return token;
}

async function readSlackResponse(response, method) {
  const body = await response.json().catch(() => null);

  if (!response.ok || !body?.ok) {
    const reason = body?.error ?? `HTTP ${response.status}`;
    throw new Error(`${method} failed: ${reason}`);
  }

  return body;
}

async function callSlackApi(method, token, body, { form = false } = {}) {
  const response = await fetch(`https://slack.com/api/${method}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": form
        ? "application/x-www-form-urlencoded; charset=utf-8"
        : "application/json; charset=utf-8",
    },
    body: form
      ? new URLSearchParams(
          Object.fromEntries(
            Object.entries(body).map(([key, value]) => [
              key,
              typeof value === "string" ? value : String(value),
            ]),
          ),
        ).toString()
      : JSON.stringify(body),
  });

  return readSlackResponse(response, method);
}

server.registerTool(
  "slack_upload_markdown",
  {
    description:
      "Upload Markdown content as a downloadable .md file to a specific Slack thread. Use the locked parent CHANNEL_ID and THREAD_TS; do not create a Canvas.",
    inputSchema: {
      filename: z
        .string()
        .min(1)
        .max(255)
        .regex(/^[A-Za-z0-9._-]+\.md$/i)
        .describe("Download filename ending in .md; no directory path"),
      content: z
        .string()
        .min(1)
        .describe("Complete UTF-8 Markdown file content"),
      channel_id: z
        .string()
        .regex(CHANNEL_ID_PATTERN)
        .describe("Target Slack channel ID, starting with C or G"),
      thread_ts: z
        .string()
        .regex(THREAD_TS_PATTERN)
        .describe("Timestamp of the parent message receiving the file reply"),
      initial_comment: z
        .string()
        .min(1)
        .max(5000)
        .optional()
        .describe("Optional message posted with the uploaded file"),
    },
  },
  async ({ filename, content, channel_id, thread_ts, initial_comment }) => {
    try {
      const token = getSlackToken();
      const fileBytes = Buffer.from(content, "utf8");

      if (fileBytes.byteLength > MAX_MARKDOWN_BYTES) {
        throw new Error("Markdown content exceeds the 1 MiB safety limit");
      }

      // Slack rejects JSON bodies for this method with invalid_arguments;
      // form-urlencoded is required in practice.
      const uploadTicket = await callSlackApi(
        "files.getUploadURLExternal",
        token,
        {
          filename,
          length: fileBytes.byteLength,
        },
        { form: true },
      );

      const uploadResponse = await fetch(uploadTicket.upload_url, {
        method: "POST",
        headers: {
          "Content-Type": "application/octet-stream",
        },
        body: fileBytes,
      });

      if (!uploadResponse.ok) {
        throw new Error(`Slack file transfer failed: HTTP ${uploadResponse.status}`);
      }

      const completed = await callSlackApi(
        "files.completeUploadExternal",
        token,
        {
          files: [{ id: uploadTicket.file_id, title: filename }],
          channel_id,
          thread_ts,
          ...(initial_comment ? { initial_comment } : {}),
        },
      );

      const file = completed.files?.[0];
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify({
              ok: true,
              file_id: file?.id ?? uploadTicket.file_id,
              filename,
              channel_id,
              thread_ts,
              permalink: file?.permalink,
            }),
          },
        ],
      };
    } catch (error) {
      return {
        isError: true,
        content: [
          {
            type: "text",
            text: error instanceof Error ? error.message : "Unknown upload error",
          },
        ],
      };
    }
  },
);

await server.connect(new StdioServerTransport());
