# --- 1) Compila o CSS do Tailwind ----------------------------------------------
FROM node:20-alpine AS css
WORKDIR /app
COPY package.json tailwind.config.js ./
RUN npm install --no-audit --no-fund
COPY assets ./assets
COPY templates ./templates
COPY apps ./apps
COPY static ./static
RUN npm run build:css

# --- 2) Aplicação Django ---------------------------------------------------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
COPY --from=css /app/static/css/app.css ./static/css/app.css
RUN DJANGO_SECRET_KEY=build-only DJANGO_DEBUG=0 python manage.py collectstatic --noinput
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-3} --timeout 60 --access-logfile -"]
