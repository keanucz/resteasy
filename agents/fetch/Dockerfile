# The Fetch.ai agents (coordinator + one per family member) for deploy/compose.yml's "fetch" profile.
# Same image for every agent; the compose command picks the script. Agent storage (roster members,
# away dates, chat history) is a JSON file in the working directory, so /data is a volume.
FROM python:3.12-slim
RUN pip install --no-cache-dir "uagents==0.25.5" "uagents-core==0.4.9" "anthropic>=2.3" "httpx>=0.27"
COPY *.py README.md /app/
WORKDIR /data
