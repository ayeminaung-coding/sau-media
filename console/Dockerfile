# Build the console, then serve it as static files. Nothing from the build
# stage reaches the runtime image — nginx ships the bundle, not node.

FROM node:22-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# The API base is baked in at build time. It can still be overridden per
# browser from the console's own Endpoint panel.
ARG VITE_API_BASE_URL=http://localhost:8001
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
