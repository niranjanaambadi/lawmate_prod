# extension/Dockerfile
# Builds the extension in a containerized environment

FROM node:18-alpine

WORKDIR /app

# Copy package files
COPY package.json ./

# Install dependencies
RUN npm install

# Copy source code
COPY . .

# Build extension
RUN npm run build

# Create ZIP
RUN npm run zip

# Output artifact
CMD ["sh", "-c", "cp lawmate-extension.zip /output/"]