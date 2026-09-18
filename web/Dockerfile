# Build stage
FROM node:20-slim AS build
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm ci || npm install
COPY web/ ./
ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Serve stage
FROM nginx:alpine
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD wget -qO- http://localhost/ || exit 1
