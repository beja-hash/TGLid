FROM node:22-alpine AS builder
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN pnpm install --frozen-lockfile
COPY apps/web apps/web
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_CSRF_COOKIE_NAME=tglid_csrf
ARG NEXT_PUBLIC_CSRF_HEADER_NAME=X-CSRF-Token
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_CSRF_COOKIE_NAME=$NEXT_PUBLIC_CSRF_COOKIE_NAME
ENV NEXT_PUBLIC_CSRF_HEADER_NAME=$NEXT_PUBLIC_CSRF_HEADER_NAME
RUN pnpm --dir apps/web build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup --system --gid 1001 nextjs && adduser --system --uid 1001 nextjs
COPY --from=builder /app/apps/web/.next/standalone ./
COPY --from=builder /app/apps/web/.next/static ./apps/web/.next/static
WORKDIR /app/apps/web
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
