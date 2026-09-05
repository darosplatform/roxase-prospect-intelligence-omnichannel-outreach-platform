FROM node:22.11.0-slim AS base

ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

EXPOSE 3000
CMD ["npm", "start"]
