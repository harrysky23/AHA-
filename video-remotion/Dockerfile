FROM node:22-bookworm-slim@sha256:e9f565d32859f0cbfb52125eafe8be39390f24dac302dc3cdf566e8ba3ab21ee
RUN apt-get update && apt-get install -y --no-install-recommends chromium ffmpeg fonts-noto-cjk && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/aha
COPY package*.json ./
RUN npm ci --ignore-scripts --no-fund --no-audit && npm cache clean --force
COPY src ./src
COPY render.mjs tsconfig.json ./
COPY isolated ./isolated
USER 65532:65532
ENV HOME=/tmp TMPDIR=/tmp LANG=C.UTF-8
ENTRYPOINT ["node", "/opt/aha/isolated/run.mjs"]
