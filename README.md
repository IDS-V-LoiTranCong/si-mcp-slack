# si-mcp-slack

Daily Report automation instructions and a custom stdio MCP server that uploads
Markdown reports as downloadable files in Slack threads.

## Prerequisites

- Node.js 20 or newer in the Cursor Cloud Agent environment.
- A Slack User OAuth token (`xoxp-...`) with the `files:write` user scope.
- The token owner must be a member of every destination channel.

No Slack bot needs to be invited to a channel. Never commit the user token.

## Install

```sh
npm ci
```

## Cursor custom MCP configuration

Add a custom **stdio** MCP server in Cursor. Use this JSON and replace only the
token value in Cursor's encrypted configuration:

```json
{
  "mcpServers": {
    "slack-upload": {
      "command": "node",
      "args": ["mcp/slack-upload-server.mjs"],
      "env": {
        "SLACK_USER_TOKEN": "xoxp-YOUR-USER-TOKEN"
      }
    }
  }
}
```

For a personal Cloud Agent, add it from the MCP menu at
<https://cursor.com/agents>. For a team-owned Automation, an admin must add it
under **Dashboard → Integrations & MCP**.

The Automation must use this repository so that
`mcp/slack-upload-server.mjs` exists in its checkout. Ensure the environment
setup runs `npm ci`.

## Tool

The server exposes `slack_upload_markdown` with these inputs:

- `filename`: filename ending in `.md`, without a directory path.
- `content`: complete Markdown content.
- `channel_id`: locked Slack channel ID (`C...` or `G...`).
- `thread_ts`: locked parent-message timestamp.
- `initial_comment`: optional message accompanying the file.

The tool uses Slack's supported external upload flow:
`files.getUploadURLExternal` → file transfer →
`files.completeUploadExternal`.

## Verify locally

```sh
npm run check
```
