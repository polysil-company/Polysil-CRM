# syntax=docker/dockerfile:1
# The frontend (the shared repo's Frontend/, integration branch), built on the
# staging box. Copied into the checkout as Dockerfile.polysil by redeploy.sh, so
# the frontend track's tree is never edited.
#
# Build-time values are inlined into the bundle (NEXT_PUBLIC_*), and next.config
# reads API_PROXY_TARGET when it loads, at build and at start alike.

FROM node:24-bookworm-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1 \
    HUSKY=0 \
    NODE_OPTIONS=--max-old-space-size=2048
COPY package.json package-lock.json .npmrc ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG RELEASE=unknown
ENV NEXT_PUBLIC_APP_ENV=staging \
    NEXT_PUBLIC_API_BASE_URL=/api/v1 \
    NEXT_PUBLIC_API_MOCKING=disabled \
    NEXT_PUBLIC_RELEASE=${RELEASE} \
    API_PROXY_TARGET=http://polysil-api:8000
# no prune: next start loads next.config.ts, and a pruned tree risks what that needs
RUN npm run build

FROM node:24-bookworm-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_APP_ENV=staging \
    API_PROXY_TARGET=http://polysil-api:8000 \
    LOG_LEVEL=info \
    PORT=3000
COPY --from=build --chown=node:node /app/package.json /app/next.config.ts /app/tsconfig.json ./
COPY --from=build --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/.next ./.next
COPY --from=build --chown=node:node /app/public ./public
USER node
EXPOSE 3000
CMD ["node_modules/.bin/next", "start", "-p", "3000", "-H", "0.0.0.0"]
