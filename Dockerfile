FROM mcr.microsoft.com/dotnet/sdk:8.0-bookworm-slim AS nwd-tools
RUN dotnet tool install NwcIO.Cli --version 0.17.0 --tool-path /opt/nwd
FROM mcr.microsoft.com/dotnet/runtime:8.0-bookworm-slim AS nwd-runtime
FROM scratch AS wheels
FROM python:3.13-slim-bookworm AS viewer
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 PID_DATA_ROOT=/library/cad-workbench PID_PORT=8765 HOME=/home/workbench
WORKDIR /opt/workbench
COPY cad-workbench/requirements.txt .
RUN --mount=from=wheels,target=/wheels if ls /wheels/*.whl >/dev/null 2>&1; then pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt; else pip install --no-cache-dir -r requirements.txt; fi
RUN groupadd -g 1000 workbench && useradd -m -u 1000 -g 1000 workbench && install -d -o workbench -g workbench /library/cad-workbench
COPY cad-workbench/ ./
USER 1000:1000
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health',timeout=4).read()"
ENV PID_VAULT=/vault
CMD ["python", "production.py"]

FROM viewer AS cad
USER root
COPY --from=nwd-tools /opt/nwd /opt/nwd
COPY --from=nwd-runtime /usr/share/dotnet /usr/share/dotnet
ENV DOTNET_ROOT=/usr/share/dotnet PID_NWD_CONVERTER=/opt/nwd/nwcio

RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources && apt-get update && apt-get install -y --no-install-recommends libicu72 libssl3 libgl1 libegl1 libfontconfig1 libxkbcommon0 libdbus-1-3 libxcb-cursor0 libxkbcommon-x11-0 && rm -rf /var/lib/apt/lists/*
RUN apt-get update && apt-get install -y --no-install-recommends xvfb xauth libopengl0 libglib2.0-0 libxcb-keysyms1 libxcb-icccm4 libxcb-xinerama0 libxcb-randr0 && rm -rf /var/lib/apt/lists/*
COPY --chmod=755 docker/oda-headless.sh /opt/workbench/oda-headless
COPY docker/runtime/NotoSansCJKsc-Regular.otf /usr/local/share/fonts/NotoSansCJKsc-Regular.otf
COPY docker/runtime/OFL.txt /usr/local/share/doc/noto/OFL.txt
ENV PID_DWG_CONVERTER=/opt/workbench/oda-headless PID_CAD_FONT=/usr/local/share/fonts/NotoSansCJKsc-Regular.otf
USER 1000:1000
