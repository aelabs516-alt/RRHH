FROM python:3.12-slim

# Environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PORT 8000

# Set work directory
WORKDIR /app

# Install system dependencies (including dependencies for WeasyPrint/xhtml2pdf)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    python3-dev \
    postgresql-client \
    libpango-1.0-0 \
    libharfbuzz0b \
    libpangoft2-1.0-0 \
    libffi-dev \
    libjpeg-dev \
    libopenjp2-7-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . /app/

# Create media and data directories for persistence
RUN mkdir -p /app/media /app/data

# Collect static files
RUN python manage.py collectstatic --noinput

# Expose port
EXPOSE 8000

# Entrypoint to run migrations and then gunicorn
CMD ["sh", "-c", "python manage.py migrate && gunicorn core.wsgi:application --bind 0.0.0.0:$PORT --workers 3"]
