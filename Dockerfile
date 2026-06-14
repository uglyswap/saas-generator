FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for pycairo (needed by xhtml2pdf for PDF export)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2-dev pkg-config python3-dev gcc && \
    rm -rf /var/lib/apt/lists/*

# Install dependencies (gunicorn est deja epingle dans requirements.txt)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create writable dirs and run as a non-root user (durcissement securite).
# NB : exports/ et instance/ sont des volumes en compose ; pour l'ecriture sous
# cet UID, le host doit accorder les droits (ou utiliser un volume nomme).
RUN mkdir -p exports instance && \
    useradd -m -u 10001 appuser && \
    chown -R appuser:appuser /app

# Environment variables
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

USER appuser

# Expose port
EXPOSE 5000

# Healthcheck applicatif (endpoint /health non authentifie)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=3).status==200 else 1)"

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
