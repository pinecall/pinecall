# The gateway's and the workers' image on a server (server.yaml): this release of pinecall-runtime with
# every voice plugin, installed from PyPI, or from the wheel `setup --from` put in wheels/.
FROM docker.io/library/python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
ARG SPEC
COPY wheels/ /wheels/
RUN pip install --no-cache-dir "${SPEC}"
