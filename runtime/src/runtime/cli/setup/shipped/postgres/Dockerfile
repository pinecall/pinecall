# The Postgres of the laptop and of its suites: 17, with pgvector and pg_textsearch, the two
# halves of hybrid search. A cluster's is images/postgres, the same two on CloudNativePG's image.

# Fully qualified: podman refuses a short name that docker would resolve against Docker Hub.
# The digest is the multi-architecture index's, so a Mac and the box build on the same bytes.
ARG POSTGRES_IMAGE=docker.io/library/postgres:17.11-trixie@sha256:d74eeac9a635390a49bc21bd49fccd973de707e2a53a76ac49b552b8712ec46f

FROM ${POSTGRES_IMAGE} AS build
ARG PGVECTOR_TAG=v0.8.6
ARG PG_TEXTSEARCH_TAG=v1.4.0
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential ca-certificates git postgresql-server-dev-17 \
 && rm -rf /var/lib/apt/lists/*
# pgvector builds with -march=native unless told otherwise, and that binary dies with SIGILL on
# any other CPU.
RUN git clone --depth 1 --branch ${PGVECTOR_TAG} https://github.com/pgvector/pgvector.git /build/pgvector \
 && make -C /build/pgvector OPTFLAGS="" && make -C /build/pgvector install DESTDIR=/out
RUN git clone --depth 1 --branch ${PG_TEXTSEARCH_TAG} https://github.com/timescale/pg_textsearch.git /build/pg_textsearch \
 && make -C /build/pg_textsearch && make -C /build/pg_textsearch install DESTDIR=/out

# Only what the two extensions installed. The build stage's apt brings the newest minor of Postgres
# with the headers, whatever the base is pinned at: its whole lib directory, copied over the base,
# put 17.12's plpgsql.so on a 17.11 server the day 17.12 came out, and initdb died on a symbol.
FROM ${POSTGRES_IMAGE}
COPY --from=build /out/usr/lib/postgresql/17/lib/ /usr/lib/postgresql/17/lib/
COPY --from=build /out/usr/share/postgresql/17/extension/ /usr/share/postgresql/17/extension/
# pg_textsearch keeps BM25 statistics in shared memory: CREATE EXTENSION fails unless preloaded.
RUN echo "shared_preload_libraries = 'pg_textsearch'" >> /usr/share/postgresql/17/postgresql.conf.sample
# Readable by the server's own user whatever the mode it was written with: under a umask of 077 the
# file arrived owner-only, psql was refused it, and the database was left made with no extension.
COPY --chmod=0644 extensions.sql /docker-entrypoint-initdb.d/10-extensions.sql
# What a server backs its database up with (archive-wal, backup-nightly): Barman's tools for an
# object store, the ones CloudNativePG's plugin runs in a cluster, and the two stores' libraries.
# Amazon's is Debian's package. Google's is no package of Debian's, and pip would replace the
# packages Debian installed to make room for it (it refuses: "Cannot uninstall requests"), so it
# goes to a folder of its own that Python is told to read, and Debian's stay as they are.
ARG GOOGLE_CLOUD_STORAGE=3.17.1
RUN apt-get update \
 && apt-get install -y --no-install-recommends barman-cli-cloud python3-boto3 python3-pip \
 && python3 -m pip install --no-cache-dir --target /usr/local/lib/barman-stores "google-cloud-storage==${GOOGLE_CLOUD_STORAGE}" \
 && apt-get purge -y python3-pip && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*
ENV PYTHONPATH=/usr/local/lib/barman-stores
COPY --chmod=0755 archive-wal backup-nightly /usr/local/bin/
