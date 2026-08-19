FROM node:20-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Production serves the built assets; compose overrides this with `npm run dev`.
RUN npm run build || true
CMD ["npm", "run", "preview"]
