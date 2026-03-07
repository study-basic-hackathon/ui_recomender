FROM python:3.13-slim

# Install Node.js 22 and system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    curl \
    git \
    wget \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libc6 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libexpat1 \
    libfontconfig1 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libstdc++6 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxshmfence1 \
    libxss1 \
    libxtst6 \
    xdg-utils \
    fonts-unifont \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Install Playwright MCP with pinned version and its bundled Chromium
RUN npm install -g @playwright/mcp@0.0.68 && \
    cd /usr/lib/node_modules/@playwright/mcp && \
    npx playwright install chromium

# Install ui-ux-pro-max design intelligence tool
RUN npm install -g uipro-cli

# Install GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | \
    dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | \
    tee /etc/apt/sources.list.d/github-cli.list > /dev/null && \
    apt-get update && apt-get install -y gh && rm -rf /var/lib/apt/lists/*

# Install Claude Agent SDK and boto3 (S3 access)
RUN pip install --no-cache-dir claude-agent-sdk==0.1.44 boto3==1.42.58

# Configure git identity for commits inside worker pods
RUN git config --global user.name "Claude Code" && \
    git config --global user.email "noreply@anthropic.com"

# Copy worker scripts
COPY docker/worker-entrypoint.sh /usr/local/bin/worker-entrypoint.sh
COPY docker/prompts.py /usr/local/bin/prompts.py
COPY docker/worker_common.py /usr/local/bin/worker_common.py
COPY docker/worker-analyze.py /usr/local/bin/worker-analyze.py
COPY docker/worker-implement.py /usr/local/bin/worker-implement.py
COPY docker/worker-createpr.py /usr/local/bin/worker-createpr.py
RUN chmod +x /usr/local/bin/worker-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/worker-entrypoint.sh"]
