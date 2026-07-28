FROM node:20-slim

WORKDIR /app

# No Chromium/Puppeteer needed — Evolution API handles WhatsApp protocol externally

# Install Node deps
COPY package*.json ./
RUN npm ci --production

# Copy app
COPY . .

# Expose port
EXPOSE 3001

# Start gateway adapter
CMD ["node", "src/index.js"]
