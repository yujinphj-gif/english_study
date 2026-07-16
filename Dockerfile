FROM python:3.13-slim-bookworm

# MSSQL ODBC 드라이버 설치 (pyodbc가 필요로 함) + pyodbc 빌드용 컴파일러
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl gnupg ca-certificates unzip build-essential unixodbc \
    && curl -sSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
        > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql17 unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# EasyOCR 모델을 빌드 타임에 미리 받아둠 (첫 요청에서 느린 다운로드가 걸리지 않도록)
RUN mkdir -p /root/.EasyOCR/model \
    && curl -L -o /root/.EasyOCR/model/craft_mlt_25k.zip \
        https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/craft_mlt_25k.zip \
    && curl -L -o /root/.EasyOCR/model/english_g2.zip \
        https://github.com/JaidedAI/EasyOCR/releases/download/v1.3/english_g2.zip \
    && unzip -o /root/.EasyOCR/model/craft_mlt_25k.zip -d /root/.EasyOCR/model \
    && unzip -o /root/.EasyOCR/model/english_g2.zip -d /root/.EasyOCR/model \
    && rm /root/.EasyOCR/model/craft_mlt_25k.zip /root/.EasyOCR/model/english_g2.zip

COPY . .

ENV FLASK_DEBUG=0
EXPOSE 8000

CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120"]
