FROM node:20-bookworm-slim

ARG TODO2CODE_COMMIT=5f8e8314dafb3ba61bd5501136eba87c21292631
ARG F2MD_COMMIT=b4bf25d5e1903b0a215d37285becc98ee9b48d50

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --filter=blob:none https://github.com/semcod/todo2code.git /opt/todo2code \
    && git -C /opt/todo2code checkout --detach "$TODO2CODE_COMMIT" \
    && cd /opt/todo2code \
    && npm ci --no-audit --no-fund \
    && npm run build

RUN python3 -m venv /opt/dodsl-venv \
    && /opt/dodsl-venv/bin/pip install --no-cache-dir \
      "f2md @ git+https://github.com/bioxfoundry/twin-dsl.git@${F2MD_COMMIT}#subdirectory=py/f2md" \
      "markitdown>=0.1,<1" "protobuf>=6.30,<7" "PyYAML>=6,<7"

WORKDIR /app
COPY . .
RUN /opt/dodsl-venv/bin/pip install --no-cache-dir --no-deps .

ENV PATH="/opt/dodsl-venv/bin:${PATH}" \
    DODSL_PROJECTS_ROOT=/data/projects \
    DODSL_HOST=0.0.0.0 \
    DODSL_PORT=8788 \
    TODO2CODE_COMMAND="node /opt/todo2code/dist/src/cli.js" \
    ONLYDSL_SSOT_COMMAND="python3 /opt/onlydsl/server.py ssot"

EXPOSE 8788
HEALTHCHECK --interval=10s --timeout=3s --retries=10 CMD node -e "fetch('http://127.0.0.1:8788/health').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"
CMD ["dodsl", "serve"]
