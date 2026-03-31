FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for pycairo (needed by xhtml2pdf for PDF export)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2-dev pkg-config python3-dev gcc && \
    rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy application
COPY . .

# Create exports directory
RUN mkdir -p exports

# Environment variables
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 5000

# Run with gunicorn
CMD ["gunicorn", \
     "-k", "gevent", \
     "-w", "4", \
     "-b", "0.0.0.0:5000", \
     "--timeout", "300", \
     "--graceful-timeout", "300", \
     "--keep-alive", "65", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app:create_app('production')"]
