FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/symphony:/home/james/homelab/automation/homelab-stack/src \
    OPENCODE_BIN=/usr/local/bin/opencode

WORKDIR /app

RUN groupadd --gid 1001 symphony \
    && useradd --uid 1001 --gid symphony --home-dir /app --shell /usr/sbin/nologin symphony

COPY pyproject.toml /app/symphony/pyproject.toml
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir "httpx>=0.27" "pyyaml>=6.0.3"

COPY . /app/symphony
RUN chown -R symphony:symphony /app

USER symphony

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "import os, shutil, urllib.request; url=os.environ['PLANE_API_URL'].rstrip('/') + '/api/v1/'; key=os.environ.get('PLANE_API_KEY', ''); req=urllib.request.Request(url, headers={'X-API-Key': key} if key else {}); urllib.request.urlopen(req, timeout=5).close(); assert shutil.which(os.environ.get('OPENCODE_BIN', '/usr/local/bin/opencode'))"

ENTRYPOINT ["python", "-m", "symphony.main"]
