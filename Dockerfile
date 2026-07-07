# Stage 1: Build React frontend
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend + built frontend
FROM python:3.10-slim
WORKDIR /app

# Defense-in-depth: the app already timestamps everything in IST explicitly
# (see backend/config.py's now_ist()), independent of container timezone.
# This just makes any OTHER incidental naive datetime.now() (e.g. inside a
# third-party library) default correctly too, instead of the python:3.10-
# slim base image's UTC default.
ENV TZ=Asia/Kolkata

# Install Python dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Copy root-level config files
COPY admin_config.json templates.json ./

# Copy built frontend from Stage 1
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

EXPOSE 8000
WORKDIR /app/backend
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
