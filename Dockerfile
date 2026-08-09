FROM node:20-bookworm-slim

ARG TODO2CODE_COMMIT=2380dd8b2f7d4bdc594613701eb770d7e251d0b3
ARG F2MD_COMMIT=c010b499feacb80fcb814be78b07d6a14444ee6f
ARG ONLYDSL_PACKAGES_COMMIT=f694d1eaa2683c6f7e72064ddb145db9802cc847

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --filter=blob:none https://github.com/semcod/todo2code.git /opt/todo2code \
    && git -C /opt/todo2code checkout --detach "$TODO2CODE_COMMIT" \
    && cd /opt/todo2code \
    && npm ci --no-audit --no-fund \
    && npm run build

RUN git clone --filter=blob:none https://github.com/tom-sapletta-com/onlyDSL.git /opt/onlydsl \
    && git -C /opt/onlydsl checkout --detach "$ONLYDSL_PACKAGES_COMMIT"

RUN git clone --filter=blob:none https://github.com/bioxfoundry/twin-dsl.git /opt/twin-dsl \
    && git -C /opt/twin-dsl checkout --detach "$F2MD_COMMIT"

RUN python3 -m venv /opt/dodsl-venv \
    && /opt/dodsl-venv/bin/pip install --no-cache-dir \
      /opt/onlydsl/packages/onlydsl-contracts \
      /opt/onlydsl/packages/onlydsl-core \
      /opt/onlydsl/packages/onlydsl-ssot \
      /opt/onlydsl \
      /opt/twin-dsl/py/f2md \
      "markitdown>=0.1,<1" "protobuf>=6.30,<7" "PyYAML>=6,<7"

WORKDIR /app
COPY . .
RUN /opt/dodsl-venv/bin/pip install --no-cache-dir --no-deps \
      ./packages/dodsl-contracts \
      ./packages/dodsl-core \
      ./packages/dodsl-planning \
      ./packages/dodsl-adapters \
      ./apps/dodsl-service

ENV PATH="/opt/dodsl-venv/bin:${PATH}" \
    DODSL_PROJECTS_ROOT=/data/projects \
    DODSL_HOST=0.0.0.0 \
    DODSL_PORT=8788 \
    TODO2CODE_COMMAND="node /opt/todo2code/dist/src/cli.js" \
    ONLYDSL_SSOT_COMMAND="onlydsl ssot"

EXPOSE 8788
HEALTHCHECK --interval=10s --timeout=3s --retries=10 CMD node -e "fetch('http://127.0.0.1:8788/health').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"
CMD ["dodsl", "serve"]
