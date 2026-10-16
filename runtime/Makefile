# check · test · db · hooks · local · tf-* · image · suite · deploy · hosting · restore-from-box · logs.

# The laptop's Postgres and Redis, for the suites only: in colima, on tmpfs, thrown away with
# their containers.
DB_IMAGE  = pinecall/postgres:17-pgvector0.8.6-pgtextsearch1.4.0
DB_NAME   = pinecall-test-postgres
DB_PORT  ?= 55432
LOCAL_DSN = postgresql://pinecall:pinecall@127.0.0.1:$(DB_PORT)/pinecall
REDIS_IMAGE = docker.io/library/redis:8.10.2-alpine
REDIS_NAME  = pinecall-test-redis
REDIS_PORT ?= 56379
LOCAL_REDIS = redis://127.0.0.1:$(REDIS_PORT)/1
T        ?= tests

# A world's cluster: its Terraform root ($(INFRA)/terraform/environments/<ENV>), and the operator's
# own of it, which no public tree holds: OPS (PINECALL_OPS, else ../../ops, beside the
# repository's checkout) has <ENV>.mk (PROJECT, and REGION, ZONE or CONTEXT where they are not
# these), values/<ENV>.yaml ($(INFRA)/values/example.yaml is one) and terraform/<ENV>.tfvars and
# <ENV>.backend.hcl. Google's credentials are the gcloud
# login's, handed over as a short-lived token in the environment, never printed.
ENV      ?= staging
OPS      ?= $(abspath $(or $(PINECALL_OPS),../../ops))
# The repository's infra/: the charts, the images, the Terraform, beside this package.
INFRA    ?= ../infra
-include $(OPS)/$(ENV).mk
VALUES    = $(OPS)/values/$(ENV).yaml
REGION   ?= us-central1
ZONE     ?= $(REGION)-c
CONTEXT  ?= gke_$(PROJECT)_$(ZONE)_pinecall-$(ENV)
TF        = terraform -chdir=$(INFRA)/terraform/environments/$(ENV)
TF_AUTH   = GOOGLE_OAUTH_ACCESS_TOKEN="$$(gcloud auth print-access-token)"
TF_ROOTS  = $(INFRA)/terraform/bootstrap $(INFRA)/terraform/project $(wildcard $(INFRA)/terraform/environments/*)

check:            ## ruff (lint, format), pyright and mypy strict, alembic check, the suites with no database; terraform's form
	uv run ruff check . && uv run ruff format --check .
	uv run pyright && uv run mypy src
	uv run pytest -q -n auto tests/conventions tests/wire
	@if command -v terraform >/dev/null; then $(MAKE) --no-print-directory tf-check; fi

# Its own data directory: a root module initialized against its bucket would be reached again.
tf-check:         ## every root module formatted and valid, with no backend reached
	terraform fmt -check -recursive $(INFRA)/terraform
	@for root in $(TF_ROOTS); do \
	  data=$(CURDIR)/.terraform-check/$$(basename $$root); \
	  TF_DATA_DIR=$$data terraform -chdir=$$root init -backend=false -input=false >/dev/null && \
	  TF_DATA_DIR=$$data terraform -chdir=$$root validate -no-color >/dev/null || exit 1; \
	done

tf-init:          ## ENV=staging: the root module's providers and its state in the bucket
	$(TF_AUTH) $(TF) init -input=false -backend-config=$(OPS)/terraform/$(ENV).backend.hcl

# Saved, so what is applied is exactly what was read.
tf-plan:          ## ENV=…: what an apply would change, saved as its plan; "No changes." is the norm
	$(TF_AUTH) $(TF) plan -input=false -var-file=$(OPS)/terraform/$(ENV).tfvars -out=plan

tf-apply:         ## ENV=…: the saved plan applied, after it was read
	$(TF_AUTH) $(TF) apply -input=false plan

# The runtime whole on this laptop (`pinecall-runtime local`): Postgres, Redis and LiveKit in docker, the
# gateway and a worker from the checkout, on the settings `make local` wrote to .local/env.
LOCAL_RUN = set -a; . ./.local/env; set +a; uv run pinecall-runtime
local:            ## Postgres, Redis and LiveKit in docker, the schema migrated, .local/env written once
	uv run pinecall-runtime local --dir .local up --services-only

local-gateway:    ## the gateway from the checkout on 127.0.0.1:8080, against `make local`
	$(LOCAL_RUN) gateway

local-worker:     ## a worker of the sandbox fleet from the checkout, against `make local`
	$(LOCAL_RUN) worker start

local-down:       ## the compose stopped; its Postgres volume and .local/env kept
	uv run pinecall-runtime local --dir .local down

test: db          ## every suite (or T=tests/calls), on the local Postgres and Redis, on every core
	DATABASE_URL=$(LOCAL_DSN) PINECALL_REDIS_URL=$(LOCAL_REDIS) uv run pytest -q -n auto $(T)

# Durability is off: a test database that loses its last second on a crash loses nothing.
db:               ## the local Postgres and Redis: colima up, the image built once, both running
	@colima status >/dev/null 2>&1 || colima start
	@docker image inspect $(DB_IMAGE) >/dev/null 2>&1 || docker build -t $(DB_IMAGE) $(INFRA)/local/postgres
	@docker inspect -f '{{.State.Running}}' $(DB_NAME) 2>/dev/null | grep -q true || { \
	  docker rm -f $(DB_NAME) >/dev/null 2>&1; \
	  docker run -d --name $(DB_NAME) -p 127.0.0.1:$(DB_PORT):5432 --tmpfs /var/lib/postgresql/data \
	    -e POSTGRES_USER=pinecall -e POSTGRES_PASSWORD=pinecall -e POSTGRES_DB=pinecall $(DB_IMAGE) \
	    -c fsync=off -c synchronous_commit=off -c full_page_writes=off >/dev/null; }
	@until docker exec $(DB_NAME) pg_isready -U pinecall -d pinecall >/dev/null 2>&1; do sleep 1; done
	@docker inspect -f '{{.State.Running}}' $(REDIS_NAME) 2>/dev/null | grep -q true || { \
	  docker rm -f $(REDIS_NAME) >/dev/null 2>&1; \
	  docker run -d --name $(REDIS_NAME) -p 127.0.0.1:$(REDIS_PORT):6379 --tmpfs /data $(REDIS_IMAGE) \
	    redis-server --save '' --appendonly no >/dev/null; }
	@until docker exec $(REDIS_NAME) redis-cli ping >/dev/null 2>&1; do sleep 1; done

hooks:            ## the pre-commit hook: `make check` when a commit touches runtime/
	git config core.hooksPath runtime/.githooks

# The runtime's image, built by Cloud Build as the builds' own identity ($(INFRA)/terraform/modules/
# build), never on the laptop. Its context is the Containerfile and this checkout's wheel alone;
# its tag is the commit, so a cluster runs exactly what the commit holds: the wheel is built from
# the working tree with the console and the widget beside it (../console, ../widget), so
# the three must be the commit, with nothing changed and nothing new in them, and TAG must name
# that commit.
REGISTRY ?= $(REGION)-docker.pkg.dev/$(PROJECT)/pinecall
BUILDER  ?= projects/$(PROJECT)/serviceAccounts/pinecall-build@$(PROJECT).iam.gserviceaccount.com
TAG      ?= $(shell git rev-parse --short HEAD)
image:            ## the runtime's container image, TAG=<commit>, built and checked by Cloud Build
	@if [ -n "$$(git status --porcelain -- . ../console ../widget)" ]; then \
	  echo "make image: runtime/, console/ or widget/ has changes no commit holds; commit them or set them aside" >&2; \
	  exit 2; fi
	@[ "$$(git rev-parse HEAD)" = "$$(git rev-parse --verify --quiet '$(TAG)^{commit}')" ] || \
	  { echo "make image: TAG=$(TAG) is not this checkout's commit, $$(git rev-parse --short HEAD)" >&2; exit 2; }
	scripts/console
	rm -rf dist && uv build --wheel --quiet
	rm -rf .image && mkdir .image
	cp $(INFRA)/images/pinecall/Containerfile dist/pinecall_runtime-*.whl .image/
	uv export --locked --extra voice --no-dev --no-emit-project --quiet -o .image/requirements.txt
	gcloud builds submit .image --config $(INFRA)/images/pinecall/cloudbuild.yaml \
	  --service-account $(BUILDER) --substitutions _IMAGE=$(REGISTRY)/runtime:$(TAG) \
	  --project $(PROJECT) --region $(REGION); status=$$?; rm -rf .image; exit $$status

# Every suite inside the cluster, against its Postgres (CloudNativePG, the application user, no
# superuser) and a Redis made for the run: the checkout's files as they are now, built
# by Cloud Build like the runtime's image; the Job's log is the result.
suite:            ## ENV=…: every suite as a Job on the cluster, TAG=<commit>; its log printed
ifeq ($(ENV),production)
	$(error make suite runs every suite against the cluster's own Postgres: never production's)
endif
	rm -rf .suite && mkdir .suite
	git ls-files -co --exclude-standard | while read -r f; do [ -f "$$f" ] && echo "$$f"; done \
	  | tar -cf - -T - | tar -xf - -C .suite
	cp $(INFRA)/images/suite/Containerfile .suite/
	gcloud builds submit .suite --config $(INFRA)/images/cloudbuild.yaml \
	  --service-account $(BUILDER) --substitutions _IMAGE=$(REGISTRY)/suite:$(TAG) \
	  --project $(PROJECT) --region $(REGION); status=$$?; rm -rf .suite; exit $$status
	kubectl --context $(CONTEXT) delete job/suite pod/suite-redis service/suite-redis --ignore-not-found
	sed "s|SUITE_IMAGE|$(REGISTRY)/suite:$(TAG)|" $(INFRA)/manifests/suite.yaml | kubectl --context $(CONTEXT) apply -f -
	kubectl --context $(CONTEXT) wait job/suite --for=condition=complete --timeout=30m; status=$$?; \
	  kubectl --context $(CONTEXT) logs job/suite | tail -40; exit $$status

# The cluster's front door (charts/edge) and Postgres (charts/postgres), then charts/pinecall at
# the image of this commit, waiting for every workload; then the live suite against the world's
# production name.
DOMAIN    = $(shell awk '/^domain:/{print $$2; exit}' $(VALUES))
deploy:           ## ENV=staging: charts/pinecall released at TAG=<commit> (make image first)
	helm upgrade --install pinecall-edge $(INFRA)/charts/edge --kube-context $(CONTEXT) \
	  -f $(VALUES) --wait --timeout 10m
	helm upgrade --install pinecall-postgres $(INFRA)/charts/postgres --kube-context $(CONTEXT) \
	  -f $(VALUES) --wait --timeout 10m
	kubectl --context $(CONTEXT) wait cluster/pinecall-postgres --for=condition=Ready --timeout=600s
	helm upgrade --install pinecall $(INFRA)/charts/pinecall --kube-context $(CONTEXT) \
	  -f $(VALUES) --set image.tag=$(TAG) --wait --timeout 20m
	PINECALL_URL=https://$(DOMAIN) uv run pytest -q tests/live

# The hosting cluster (modules/hosting, when the environment has one): the runners of both worlds,
# at TAG=<commit>, the same image as the runtime's. Its context is the regional Autopilot cluster's.
HOSTING   = gke_$(PROJECT)_$(REGION)_pinecall-$(ENV)-hosting
hosting:          ## ENV=…: charts/hosting released on the hosting cluster at TAG=<commit>
	gcloud container clusters get-credentials pinecall-$(ENV)-hosting --region $(REGION) \
	  --project $(PROJECT) >/dev/null
	helm upgrade --install pinecall-hosting $(INFRA)/charts/hosting --kube-context $(HOSTING) \
	  --namespace pinecall-runner --create-namespace \
	  -f $(OPS)/values/hosting-$(ENV).yaml --set image.tag=$(TAG) --wait --timeout 15m

# A box's database into the cluster's Postgres, once, at its cutover (and its rehearsal on
# staging): the box's schema `public` and its rows, dumped on the box and streamed into the
# Postgres pod, never onto this laptop; the cluster's own schema emptied first and its two
# extensions made again, as initdb made them; restored as the database's owner, the extensions
# and the schema itself left out. The box's runtime must be stopped first: a row written after
# the dump is lost.
BOX      ?=
PG        = kubectl --context $(CONTEXT) exec -i pinecall-postgres-1 -c postgres --
DUMP      = /var/lib/postgresql/data/box.dump
restore-from-box: ## ENV=…: the box's database restored into the cluster's Postgres (BOX=<ssh alias>)
ifeq ($(ENV),production)
	$(error make restore-from-box empties the cluster's schema first: never on production)
endif
	@[ -n "$(BOX)" ] || { echo "make restore-from-box: BOX=<the box's ssh alias>" >&2; exit 2; }
	$(PG) psql -v ON_ERROR_STOP=1 -d pinecall -c 'DROP SCHEMA public CASCADE' \
	  -c 'CREATE SCHEMA public AUTHORIZATION pinecall' \
	  -c 'CREATE EXTENSION vector' -c 'CREATE EXTENSION pg_textsearch'
	ssh $(BOX) 'sudo podman exec pinecall-postgres pg_dump -U pinecall -d pinecall -n public -Fc --no-owner --no-privileges' \
	  | $(PG) sh -c 'cat > $(DUMP)'
	$(PG) sh -c 'pg_restore -l $(DUMP) | grep -v " EXTENSION \| COMMENT - EXTENSION \| SCHEMA - public \| COMMENT - SCHEMA public " > $(DUMP).list \
	  && pg_restore --exit-on-error --no-owner --role=pinecall -d pinecall -L $(DUMP).list $(DUMP); \
	  status=$$?; rm -f $(DUMP) $(DUMP).list; exit $$status'
	$(PG) psql -d pinecall -At -c 'select count(*) from call_log' -c 'select count(*) from schema_migrations'

logs:             ## ENV=…: the gateways' and the workers' logs of the last hour
	kubectl --context $(CONTEXT) logs --since=1h --prefix --max-log-requests 20 \
	  -l 'app in (pinecall-gateway,worker,overflow)'

.PHONY: hosting check test db hooks local local-gateway local-worker local-down tf-check tf-init tf-plan tf-apply image suite deploy restore-from-box logs
