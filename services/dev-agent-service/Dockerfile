FROM python:3.12-slim
WORKDIR /app

# git is needed for worktrees, code search and history
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

COPY services/dev-agent-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY packages/llm-client/ ./packages/llm-client/
COPY services/dev-agent-service/src/ ./src/
COPY services/dev-agent-service/mcp/ ./mcp/

ENV PORT=3007 APM_PACKAGES_DIR=/app/packages DEV_AGENT_DATA_DIR=/data
EXPOSE 3007
CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT}"]
