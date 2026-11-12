# check · test · db · hooks · local · tf-* · image · suite · deploy · fleet · hosting · restore-from-box · logs.

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

# The cluster both envs run on: one Terraform root for every cluster ($(INFRA)/terraform/cluster), told
# which one by CLUSTER (its name, its variables, its state, its own data directory), and the operator's
# own of it, which no public tree holds: OPS (PINECALL_OPS, else ../../ops, beside the
# repository's checkout) has <CLUSTER>.mk (PROJECT, and REGION, ZONE or CONTEXT where they are not
# these), values/<CLUSTER>.yaml ($(INFRA)/values/example.yaml is one), values/<CLUSTER>.terraform.json
# (written by `make values`) and terraform/<CLUSTER>.tfvars and
# <CLUSTER>.backend.hcl. Google's credentials are the gcloud
# login's, handed over as a short-lived token in the environment, never printed.
CLUSTER  ?= staging
OPS      ?= $(abspath $(or $(PINECALL_OPS),../../ops))
# The repository's infra/: the charts, the images, the Terraform, beside this package.
INFRA    ?= ../infra
-include $(OPS)/$(CLUSTER).mk
VALUES    = $(OPS)/values/$(CLUSTER).yaml
# What Terraform made, as the charts read it (`make values`); the operator's own file, read after
# it, holds decisions alone and wins where both speak.
TF_VALUES = $(OPS)/values/$(CLUSTER).terraform.json
CHART_VALUES = -f $(TF_VALUES) -f $(VALUES)
REGION   ?= us-central1
ZONE     ?= $(REGION)-c
CONTEXT  ?= gke_$(PROJECT)_$(ZONE)_pinecall-$(CLUSTER)
# Two roots go through the same rails (init, a plan that is saved and refuses to remove, the apply
# of that plan): a cluster's, and with ROOT=project what every cluster of the project shares. Until
# 2026-11-12 the project's was planned and applied by a line typed by hand, with no such refusal.
ROOT     ?= cluster
ifeq ($(ROOT),project)
TF_STATE  = project
TF_VARS   = -var-file=$(OPS)/terraform/project.tfvars
else
TF_STATE  = $(CLUSTER)
TF_VARS   = -var name=$(CLUSTER) -var-file=$(OPS)/terraform/$(CLUSTER).tfvars \
	-var-file=$(OPS)/terraform/$(CLUSTER).fence.tfvars.json
endif
TF_ROOT   = $(abspath $(INFRA)/terraform/$(ROOT))
# Each state keeps its own data directory: the cluster's root is initialised against one per cluster.
TF        = TF_DATA_DIR=$(TF_ROOT)/.terraform/$(TF_STATE) terraform -chdir=$(TF_ROOT)
TF_PLAN   = $(TF_ROOT)/$(TF_STATE).plan
TF_AUTH   = GOOGLE_OAUTH_ACCESS_TOKEN="$$(gcloud auth print-access-token)"
TF_ROOTS  = $(INFRA)/terraform/bootstrap $(INFRA)/terraform/project $(INFRA)/terraform/cluster

check:           ## ruff (lint, format), pyright and mypy strict, the convention tests; terraform's form
	uv run ruff check . && uv run ruff format --check .
	uv run pyright && uv run mypy src
	uv run pytest -q -n auto tests/conventions
	@if command -v terraform >/dev/null; then $(MAKE) --no-print-directory tf-check; fi

# Its own data directory: a root module initialized against its bucket would be reached again.
tf-check:         ## every root module formatted and valid, with no backend reached
	terraform fmt -check -recursive $(INFRA)/terraform
	@for root in $(TF_ROOTS); do \
	  data=$(CURDIR)/.terraform-check/$$(basename $$root); \
	  TF_DATA_DIR=$$data terraform -chdir=$$root init -backend=false -input=false >/dev/null && \
	  TF_DATA_DIR=$$data terraform -chdir=$$root validate -no-color >/dev/null || exit 1; \
	done

# ENV is an org's env (production or sandbox) and `make fleet` alone takes one. Until 2026-11-12 it
# named the cluster, so a target of a cluster that is given ENV, on the command line or by the
# environment, refuses: obeyed, it would act on the default cluster, whatever ENV said.
OF_A_CLUSTER = tf-init tf-fence tf-plan tf-apply values image suite diff edge postgres deploy-guards deploy rollback hosting restore-from-box logs
$(OF_A_CLUSTER): cluster-not-env
cluster-not-env:
ifneq ($(filter command environment,$(origin ENV)),)
	$(error make $(MAKECMDGOALS): the cluster is CLUSTER= since 2026-11-12, and ENV= is an org's env, which `make fleet` alone takes)
endif

tf-init:          ## CLUSTER=staging | ROOT=project: the root module's providers and its state in the bucket
	$(TF_AUTH) $(TF) init -input=false -backend-config=$(OPS)/terraform/$(TF_STATE).backend.hcl

# The networks the gateway approved for SIP, where the plan reads them: a versioned file of the
# operator's own, so a checkout never lacks it and a change to it is read as a diff before a plan.
# Written whole or not at all: a gateway that does not answer leaves the file as it was.
tf-fence:         ## CLUSTER=…: the fence's networks, from the running gateway into ops/terraform/<cluster>.fence.tfvars.json
	@fence=$(OPS)/terraform/$(CLUSTER).fence.tfvars.json; \
	kubectl --context $(CONTEXT) exec deploy/pinecall-gateway -- pinecall-runtime fence export > $$fence.new && \
	  mv $$fence.new $$fence || { rm -f $$fence.new; echo "tf-fence: the gateway did not answer; $$fence is unchanged" >&2; exit 1; }
	@git -C $(OPS) --no-pager diff --stat -- terraform/$(CLUSTER).fence.tfvars.json

# Saved, so what is applied is exactly what was read. A plan that deletes or replaces anything is
# not kept unless that was asked for (REMOVES=yes): a plan that removes what nobody asked to remove
# means an input is missing, and the thing to do is find it, never to apply around it.
tf-plan:          ## CLUSTER=… | ROOT=project [REMOVES=yes]: what an apply would change, saved as its plan; "No changes." is the norm
	$(TF_AUTH) $(TF) plan -input=false $(TF_VARS) -out=$(TF_PLAN)
	@$(TF) show -json $(TF_PLAN) | scripts/plan-removals || [ "$(REMOVES)" = yes ] || \
	  { rm -f $(TF_PLAN); echo "tf-plan: this plan removes the above and was not kept. An input is missing, or the removal is meant: REMOVES=yes" >&2; exit 2; }

# The plan holds the state it was made from, the drawn secrets in clear among it: gone once applied.
tf-apply:         ## CLUSTER=… | ROOT=project: the saved plan applied, after it was read, and then deleted
	$(TF_AUTH) $(TF) apply -input=false $(TF_PLAN); status=$$?; rm -f $(TF_PLAN); exit $$status

# The cluster's names, addresses, ranges and identities, from Terraform's state into the values the
# charts read: nothing Terraform made is typed again by hand. Run after an apply; the file is the
# operator's and versioned there, so what changed is read as a diff. Written whole or not at all.
values:           ## CLUSTER=…: what Terraform made, as the charts' values, into ops/values/<cluster>.terraform.json
	@$(TF_AUTH) $(TF) output -json chart_values | python3 -m json.tool --sort-keys > $(TF_VALUES).new && \
	  [ -s $(TF_VALUES).new ] && mv $(TF_VALUES).new $(TF_VALUES) || \
	  { rm -f $(TF_VALUES).new; echo "make values: the state has no chart_values; make tf-apply CLUSTER=$(CLUSTER) first" >&2; exit 1; }
	@git -C $(OPS) --no-pager diff --stat -- values/$(CLUSTER).terraform.json

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

# The runtime's image, built whole by Cloud Build as the builds' own identity ($(INFRA)/terraform/
# modules/build), never on the laptop. Its context is the commit's tree and nothing else (`git
# archive`): the console, the wheel and the image are built there, in the three stages of
# $(INFRA)/images/runtime/Containerfile, so what no commit holds cannot be in an image and the
# working tree may be in any state. Its tag is that commit. Until 2026-11-12 the console and the
# wheel were built here, from this laptop's node_modules, and two guards stood in for the commit.
REGISTRY ?= $(REGION)-docker.pkg.dev/$(PROJECT)/pinecall
BUILDER  ?= projects/$(PROJECT)/serviceAccounts/pinecall-build@$(PROJECT).iam.gserviceaccount.com
TAG      ?= $(shell git rev-parse --short HEAD)
# What the registry holds for TAG, by its digest: a tag can be pushed again, a digest cannot, so a
# release names both and a pod pulls the digest.
DIGEST    = $$(gcloud artifacts docker images describe $(REGISTRY)/runtime:$(TAG) --project $(PROJECT) --format='value(image_summary.digest)' 2>/dev/null)
# The image a release runs, named whole by what built it: the registry `make image` pushed to, the
# commit, the digest. No values file repeats the registry.
IMAGE     = --set image.repository=$(REGISTRY)/runtime --set image.tag=$(TAG) --set image.digest=$(DIGEST)
image:           ## the runtime's container image, TAG=<commit>, built from that commit and checked by Cloud Build
	git -C .. archive --format=tar.gz -o runtime/.image.tar.gz '$(TAG)^{commit}'
	gcloud builds submit .image.tar.gz --config $(INFRA)/images/runtime/cloudbuild.yaml \
	  --service-account $(BUILDER) --substitutions _IMAGE=$(REGISTRY)/runtime:$(TAG) \
	  --project $(PROJECT) --region $(REGION); status=$$?; rm -f .image.tar.gz; exit $$status

# Every suite inside the cluster, against its Postgres (CloudNativePG, the application user, no
# superuser) and a Redis made for the run: the checkout's files as they are now, built
# by Cloud Build like the runtime's image; the Job's log is the result.
suite:            ## CLUSTER=…: every suite as a Job on the cluster, TAG=<commit>; its log printed
ifeq ($(CLUSTER),production)
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

# Three charts, three releases, three targets. A deploy of the runtime releases charts/pinecall and
# nothing else: until 2026-11-12 it also released the front door and Postgres from whatever the
# working tree held, so an edit to charts/postgres restarted the only database on a runtime deploy.
# `make edge` and `make postgres` are run when those charts or their values change, after `make diff`.
HELM      = helm --kube-context $(CONTEXT)
CHARTS    = $(INFRA)/charts

diff:             ## CLUSTER=… TAG=<commit>: what releasing each chart would change, nothing touched (needs the helm-diff plugin)
	@$(HELM) plugin list | grep -q '^diff' || \
	  { echo "make diff: helm plugin install https://github.com/databus23/helm-diff" >&2; exit 2; }
	$(HELM) diff upgrade pinecall-edge $(CHARTS)/edge $(CHART_VALUES)
	$(HELM) diff upgrade pinecall-postgres $(CHARTS)/postgres $(CHART_VALUES)
	$(HELM) diff upgrade pinecall $(CHARTS)/pinecall $(CHART_VALUES) $(IMAGE)

edge:             ## CLUSTER=…: charts/edge released: the front door, its routes and certificates
	$(HELM) upgrade --install pinecall-edge $(CHARTS)/edge $(CHART_VALUES) --rollback-on-failure --timeout 10m

# A change to the instance's spec restarts the only instance: in a window, its diff read first.
postgres:         ## CLUSTER=…: charts/postgres released, and waited for until the database is ready
	$(HELM) upgrade --install pinecall-postgres $(CHARTS)/postgres $(CHART_VALUES) --rollback-on-failure --timeout 10m
	kubectl --context $(CONTEXT) wait cluster/pinecall-postgres --for=condition=Ready --timeout=600s

# What a deploy must find true before it touches the cluster, each refusal saying what to do:
# the charts are the ones the commit holds (a release is what a commit says, not what a tree has);
# the image exists (with none the migration's Job sat in ImagePullBackOff for twenty minutes and
# left the release failed); and no release of the chart is half-way.
deploy-guards:
	@[ -z "$$(git status --porcelain -- $(CHARTS))" ] && git diff --quiet '$(TAG)' -- $(CHARTS) || \
	  { echo "make deploy: infra/charts is not what commit $(TAG) holds; commit it or set it aside" >&2; exit 2; }
	@[ -n "$(DIGEST)" ] || \
	  { echo "make deploy: no image $(REGISTRY)/runtime:$(TAG); make image TAG=$(TAG) first" >&2; exit 2; }
	@standing=$$($(HELM) status pinecall -o json 2>/dev/null | python3 -c 'import json, sys; print(json.load(sys.stdin)["info"]["status"])' 2>/dev/null); \
	  case "$$standing" in pending-*) \
	    echo "make deploy: the release is $$standing, left by a deploy that was cut; make rollback CLUSTER=$(CLUSTER) first" >&2; exit 2;; esac

# Helm goes back to the release that ran, by itself, when the upgrade fails or is cut. The migrations
# it ran are not undone: a revision is written so the release before it still runs on its schema.
# The name the live suite knocks at is asked of the cluster, which is where it is served.
deploy: deploy-guards  ## CLUSTER=staging: charts/pinecall released at TAG=<commit> (make image first), then the live suite
	$(HELM) upgrade --install pinecall $(CHARTS)/pinecall $(CHART_VALUES) \
	  $(IMAGE) --rollback-on-failure --timeout 20m
	PINECALL_URL=https://$$(kubectl --context $(CONTEXT) get httproute pinecall -o jsonpath='{.spec.hostnames[0]}') \
	  uv run pytest -q tests/live

rollback:         ## CLUSTER=… [REV=<n>]: charts/pinecall back to the release before this one, or to revision REV
	$(HELM) history pinecall --max 5
	$(HELM) rollback pinecall $(REV) --wait --timeout 20m

# How many scaled workers an env keeps warm (32 seats and an e2-standard-8 each, ~US$195 a month),
# changed in one line: the values' `envs.<ENV>.workers.scaled` written, and committed where OPS is a
# git repository (scripts/fleet), then charts/pinecall released again at the image that runs. No image and no
# code go out, so the chart here must be the one that image's commit released.
fleet:            ## CLUSTER=… ENV=sandbox|production MIN=<n> [MOST=<n>]: that many scaled workers kept warm, at the image that runs
	@[ -n "$(ENV)" ] && [ -n "$(MIN)" ] || { echo "make fleet: ENV=sandbox|production MIN=<n>, and MOST=<n> for the ceiling" >&2; exit 2; }
	scripts/fleet $(VALUES) $(ENV) $(MIN) $(MOST)
	@set -- $$(helm get values pinecall --kube-context $(CONTEXT) -o json \
	  | python3 -c 'import json, sys; image = json.load(sys.stdin)["image"]; print(image["tag"], image.get("digest", ""))'); \
	running=$$1; pinned=$$2; \
	git diff --quiet "$$running" -- $(INFRA)/charts/pinecall || \
	  { echo "make fleet: charts/pinecall changed since $$running, the image that runs: make image && make deploy CLUSTER=$(CLUSTER)" >&2; exit 2; }; \
	$(HELM) upgrade pinecall $(CHARTS)/pinecall $(CHART_VALUES) \
	  --set image.repository=$(REGISTRY)/runtime --set image.tag=$$running \
	  $${pinned:+--set image.digest=$$pinned} --rollback-on-failure --timeout 10m

# The hosting cluster (modules/hosting, when the cluster has one): the runners of both envs,
# at TAG=<commit>, the same image as the runtime's. Its context is the regional Autopilot cluster's.
HOSTING   = gke_$(PROJECT)_$(REGION)_pinecall-$(CLUSTER)-hosting
hosting:          ## CLUSTER=…: charts/hosting released on the hosting cluster at TAG=<commit>
	gcloud container clusters get-credentials pinecall-$(CLUSTER)-hosting --region $(REGION) \
	  --project $(PROJECT) >/dev/null
	helm upgrade --install pinecall-hosting $(INFRA)/charts/hosting --kube-context $(HOSTING) \
	  --namespace pinecall-runner --create-namespace \
	  -f $(OPS)/values/hosting-$(CLUSTER).yaml $(IMAGE) \
	  --wait --timeout 15m

# A box's database into the cluster's Postgres, once, at its cutover (and its rehearsal on
# staging): the box's schema `public` and its rows, dumped on the box and streamed into the
# Postgres pod, never onto this laptop; the cluster's own schema emptied first and its two
# extensions made again, as initdb made them; restored as the database's owner, the extensions
# and the schema itself left out. The box's runtime must be stopped first: a row written after
# the dump is lost.
BOX      ?=
PG        = kubectl --context $(CONTEXT) exec -i pinecall-postgres-1 -c postgres --
DUMP      = /var/lib/postgresql/data/box.dump
restore-from-box: ## CLUSTER=…: the box's database restored into the cluster's Postgres (BOX=<ssh alias>)
ifeq ($(CLUSTER),production)
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

logs:             ## CLUSTER=…: the gateways' and the workers' logs of the last hour
	kubectl --context $(CONTEXT) logs --since=1h --prefix --max-log-requests 20 \
	  -l 'app in (pinecall-gateway,worker,overflow)'

.PHONY: hosting check test db hooks local local-gateway local-worker local-down tf-check tf-init tf-fence tf-plan tf-apply values image suite diff edge postgres deploy-guards deploy rollback fleet restore-from-box logs cluster-not-env
