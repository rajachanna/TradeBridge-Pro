FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir . && \
    useradd --uid 10001 --create-home trader && \
    mkdir -p /data && chown trader:trader /data
USER trader
ENV TB_DB_PATH=/data/tradebridge.sqlite
EXPOSE 8000
CMD ["uvicorn","tradebridge.api:app","--host","0.0.0.0","--port","8000"]
