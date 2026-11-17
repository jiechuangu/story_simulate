FROM python:3.11

RUN apt-get update \
  && apt-get install -y --no-install-recommends nodejs npm \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package.json package-lock.json ./
COPY frontend/package.json frontend/package-lock.json ./frontend/
COPY backend/requirements.txt ./backend/

RUN npm ci \
  && npm ci --prefix frontend \
  && pip install --no-cache-dir -r backend/requirements.txt

COPY . .

EXPOSE 3000 5001
CMD ["npm", "run", "dev"]
