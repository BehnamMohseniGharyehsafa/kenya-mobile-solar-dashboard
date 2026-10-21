FROM python:3.13-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYVISTA_OFF_SCREEN=true \
    MPLBACKEND=Agg \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    LP_NUM_THREADS=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libegl1 libegl-mesa0 libgl1-mesa-dri libxrender1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-cloud.txt ./
RUN pip install --no-cache-dir -r requirements-cloud.txt
RUN useradd --create-home --uid 10001 solar
COPY --chown=solar:solar . .
USER solar
ENV MPLCONFIGDIR=/tmp/matplotlib \
    PV_WEATHER_CACHE_DIR=/tmp/solar-weather
EXPOSE 10000
CMD ["gunicorn", "--config", "gunicorn.conf.py", "cloud_app:create_app()"]
