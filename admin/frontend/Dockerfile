# Build stage
FROM node:22-slim AS build
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
# Pin pnpm via corepack so the image build does not silently pick up a
# newer pnpm whose --frozen-lockfile / build-script policy differs from
# the one used to generate pnpm-lock.yaml. Bump together with the local
# pnpm version when refreshing the lockfile.
RUN corepack enable && corepack prepare pnpm@10.27.0 --activate

WORKDIR /app

# Copy package files first for better caching
COPY package.json pnpm-lock.yaml ./

# Install dependencies
RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --frozen-lockfile

# Copy source files
COPY . .

# Build argument for API URL (can be overridden at build time)
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=${VITE_API_URL}

# Build for production
RUN pnpm build

# Production stage - serve with nginx
FROM nginx:alpine AS production

# Copy built assets
COPY --from=build /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

# Development stage
FROM node:22-slim AS development
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
# Pin pnpm via corepack so the image build does not silently pick up a
# newer pnpm whose --frozen-lockfile / build-script policy differs from
# the one used to generate pnpm-lock.yaml. Bump together with the local
# pnpm version when refreshing the lockfile.
RUN corepack enable && corepack prepare pnpm@10.27.0 --activate

WORKDIR /app

COPY package.json pnpm-lock.yaml ./

RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --frozen-lockfile

# Source files will be mounted as volume in development
EXPOSE 5173

CMD ["pnpm", "dev", "--host", "0.0.0.0"]
