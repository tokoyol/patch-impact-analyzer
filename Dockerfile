FROM node:20-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NEXT_TELEMETRY_DISABLED=1 \
    API_BASE_URL=/api \
    NEXT_PUBLIC_API_BASE_URL=/api

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Install backend dependencies in a dedicated virtual environment.
COPY backend/requirements.txt /workspace/backend/requirements.txt
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r /workspace/backend/requirements.txt
ENV PATH="/opt/venv/bin:${PATH}"

# Install frontend dependencies first for better Docker layer caching.
COPY frontend/package*.json /workspace/frontend/
WORKDIR /workspace/frontend
RUN npm ci

# Copy source and build Next.js.
COPY frontend /workspace/frontend
RUN npm run build

# Copy backend source and startup script.
WORKDIR /workspace
COPY backend /workspace/backend
COPY render-start.sh /workspace/render-start.sh
RUN chmod +x /workspace/render-start.sh

EXPOSE 10000

CMD ["/workspace/render-start.sh"]
