# Use a newer, more patched Node LTS image
FROM node:22-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies and audit fix known vulnerabilities
RUN npm ci --only=production \
    && npm audit fix --audit-level=moderate || true

# Copy TypeScript source
COPY tsconfig.json .
COPY src/ ./src/

# Compile TypeScript
RUN npx tsc

# Run compiled code
CMD ["node", "dist/index.js"]