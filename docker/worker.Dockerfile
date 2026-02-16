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

# Install Playwright and Chromium (without --with-deps since deps are installed above)
RUN npm install -g playwright@1.49.0 && \
    npx playwright install chromium

# Install Claude Agent SDK
RUN pip install --no-cache-dir claude-agent-sdk

# Copy worker scripts
COPY docker/worker-entrypoint.sh /usr/local/bin/worker-entrypoint.sh
COPY docker/worker-analyze.py /usr/local/bin/worker-analyze.py
COPY docker/worker-implement.py /usr/local/bin/worker-implement.py
COPY docker/take-screenshot.mjs /usr/local/bin/take-screenshot.mjs
RUN chmod +x /usr/local/bin/worker-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/worker-entrypoint.sh"]
