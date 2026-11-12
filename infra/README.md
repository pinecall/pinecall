# infra: Pinecall on Kubernetes

The runtime on a Kubernetes cluster, from nothing, on Google Cloud. Terraform makes everything in
the cloud (the cluster and its pools, the registry, the address, the firewall, the names, the
secrets, the operators the charts rely on); three Helm charts run the runtime on it (the front
door, Postgres, the runtime), each released by its own target. Nothing is made by hand and nothing
is built on a laptop.

| path | what |
|---|---|
| `terraform/bootstrap` | the bucket every other root module keeps its state in, made once with local state |
| `terraform/project` | what every cluster of the project shares, each in a file of its own: the images' registry (`registry.tf`) and the identity Cloud Build builds them as (`build.tf`) |
| `terraform/cluster` | one cluster, the same code for every one: `CLUSTER` names it and picks its variables and its state. `production` (both environments at one name) and `staging`, made for a proof with calls and destroyed after it, are two files of values |
| `terraform/modules/gke` | a cluster: zonal, Workload Identity; a core pool both environments share, and for each environment a media node and a workers pool from 0 that the cluster autoscaler sizes alone ("A pool an environment" below) |
| `terraform/modules/secrets` | the runtime's secrets, drawn once into Secret Manager, and the identity External Secrets reads them as |
| `terraform/modules/addons` | CloudNativePG with its Barman Cloud plugin and cert-manager, External Secrets and KEDA, each its pinned chart |
| `terraform/modules/backups` | the bucket Postgres's WAL and base backups go to, and the identity that writes them, which touches it alone |
| `terraform/modules/edge` | the global address and a certificate for each name, proved by DNS before it points here, a wildcard name and certificate for the apps' own pages when `pages` names their domain, and a certificate of its own for services of the operator's own at the same endpoint (`services`); each environment's media address and its SIP name; the firewall (media open, 5060 to the carriers alone); the names in Route 53 |
| `terraform/modules/notify` | optional (`firebase_project`): the Google identity a notifier of the operator's own signs its pushes as (Firebase Cloud Messaging alone), bound to its chart's service account |
| `terraform/modules/kubeip` | the identity kubeip acts as: it gives each environment's media node the static address `modules/edge` reserves, and can do nothing else |
| `terraform/modules/hosting` | the hosting cluster, optional (`hosting = true`): GKE Autopilot in a VPC of its own, where the orgs' hosted apps run, one gVisor pod each |
| `terraform/modules/lab` | the voice lab's generator, beside a cluster made for a proof and destroyed after it (`lab = false`) |
| `terraform/modules/alerts` | the alerts on the gateways' measures, in Cloud Monitoring, and the addresses they are mailed to |
| `images/runtime/` | the runtime's image: one for every process, each a `pinecall-runtime` verb (`make image`), built from one commit in three stages |
| `images/postgres/` | the cluster's Postgres: CloudNativePG's operand image with pg_textsearch on it |
| `images/suite/` | every suite, run as a Job inside a cluster (`make suite`) |
| `images/app/` | a hosted app's pod: Node, uv and CPython 3.13, so a TypeScript or a Python project installs and runs (`charts/hosting`'s `appImage`) |
| `images/cloudbuild.yaml` | how an image is built: by Cloud Build, as the builds' own identity |
| `charts/postgres/` | the cluster's Postgres under CloudNativePG: its WAL to a bucket as it is written and a base backup each night (the Barman Cloud plugin), 35 days kept |
| `manifests/suite.yaml` | the suites' Job, with a Redis made for the run |
| `charts/pinecall/` | the runtime: two gateways and Redis on the shared core pool; each environment's LiveKit, SIP and a few workers on its media node, and its scaled workers on its own pool (KEDA, on the gateway's own number); the overflow, the migrations, the nightly retention |
| `charts/hosting/` | the hosting cluster's workloads: a runner per environment and the namespace their apps run in, fenced (`make hosting`) |
| `charts/edge/` | the front endpoint, released apart and first: the Gateway (Google's HTTPS load balancer, the Gateway API) with Certificate Manager's certificate, its routes, the HTTP redirect and the backends' policies; its load balancer takes minutes to make, so a reinstall of the runtime never makes it again |
| `values/example.yaml` · `hosting-example.yaml` | an operator's values for the charts, every one an example: copied into `OPS` (below) and filled in; CI renders and scans the charts with them |
| `lab/` | calls with real audio and the vendors faked, against staging, measured (`terraform/modules/lab` is its generator) |
| `local/` | the runtime on a laptop, and the Postgres image of the suites (`make local`, `make db`) |
| `models/` | the open stack: three model servers on one GPU and the providers row that points the runtime at them |

## Your own values

Nothing in the charts, the modules or the roots names an operator's own: every name, address,
range, account, provider and bucket is a value or a variable, and an operator's values live
outside this tree, in a directory of their own, `OPS` (`PINECALL_OPS`, else `../../ops`, beside the
repository's checkout; a private repository is the place for it). The Makefile reads it:

| `OPS/` | what |
|---|---|
| `<cluster>.mk` | `PROJECT = <the Google Cloud project>`, and `REGION`, `ZONE` or `CONTEXT` where they are not `us-central1`, `<region>-c` and `gke_<project>_<zone>_pinecall-<cluster>` |
| `values/<cluster>.terraform.json` | what Terraform made, as the charts read it: the names, the secret store's provider and prefix, the ingress, the backups' destination and identity, the ranges, the addresses. Written by `make values CLUSTER=<cluster>` from the cluster root's `chart_values` output after an apply, never typed |
| `values/<cluster>.yaml` | the decisions, read after it and winning where both speak: Postgres's image, the recordings' store, sign-up, pools and fleets (`infra/values/example.yaml` shows every key a chart reads, those of both files) |
| `values/hosting-<cluster>.yaml` | `charts/hosting`'s (`infra/values/hosting-example.yaml`) |
| `terraform/<cluster>.tfvars` | the root's variables: the project, the DNS zone, the names, the SIP names, the ranges, services of your own, the secrets you put, who alerts mail |
| `terraform/<cluster>.backend.hcl` | the state bucket and prefix (`bucket = "…"`, `prefix = "cluster/<cluster>"`), given to `make tf-init` |
| `terraform/bootstrap.tfvars` · `project.tfvars` · `project.backend.hcl` | the same for the two roots made once |

The charts never guess a provider: the secret store is the values' `secrets.provider` (on GKE with
`auth.workloadIdentity` naming the cluster and the operator's ServiceAccount, so the store never
waits on a node's metadata server — `values/example.yaml`), the front
endpoint's class and annotations `ingress`, Postgres's backups `postgres.backups` (destination,
credentials, the pods' identity), the disks' class `storageClass`, the collector
`monitoring.collector`. Unset where one is required, the release fails and says which.

## From nothing to a release

With gcloud signed in on the project, and the zone of the names on Route 53 (`~/.aws`):

```console
$ terraform -chdir=infra/terraform/bootstrap init && terraform -chdir=infra/terraform/bootstrap apply -var-file=$OPS/terraform/bootstrap.tfvars   # once
$ make tf-init ROOT=project && make tf-plan ROOT=project && make tf-apply ROOT=project   # once: the registry and the builds' identity, through the same rails as a cluster's
$ make tf-init CLUSTER=<cluster>
$ make tf-fence CLUSTER=<cluster>   # the networks the gateway approved for SIP, into the operator's own directory
$ make tf-plan CLUSTER=<cluster>    # read it; the plan is saved, unless it removes something nobody asked to remove
$ make tf-apply CLUSTER=<cluster>   # exactly the plan read, which is then deleted
$ make values CLUSTER=<cluster>     # what Terraform made, into the values the charts read; read its diff
$ gcloud container clusters get-credentials pinecall-<cluster> --zone <zone>
$ gcloud builds submit infra/images/postgres --config infra/images/cloudbuild.yaml \
    --service-account "$(terraform -chdir=infra/terraform/project output -raw build_service_account)" \
    --substitutions _IMAGE="$(terraform -chdir=infra/terraform/project output -raw registry)/postgres:17.11-pgvector0.8.6-pgtextsearch1.4.0"
$ make edge CLUSTER=<cluster>       # the front door: charts/edge, when it or its values change
$ make postgres CLUSTER=<cluster>   # Postgres: charts/postgres, when it or its values change (it may restart the instance)
$ make image                        # the runtime at this commit
$ make diff CLUSTER=<cluster>       # what releasing each chart would change, nothing touched
$ make deploy CLUSTER=<cluster>     # the runtime at that image (charts/pinecall alone), then asked at its name
$ make rollback CLUSTER=<cluster>   # the runtime back to the release before this one
$ make fleet CLUSTER=<cluster> ENV=sandbox MIN=1   # that env keeps one scaled worker warm (MIN=0 lets it go), no new image
$ make suite CLUSTER=<cluster>      # every suite inside the cluster
```

`make image` sends Cloud Build one commit's tree (`git archive` of `TAG`) and nothing of the
working tree, so an image holds what its commit holds whatever state the checkout is in. The
image is built there in three stages (`images/runtime/Containerfile`): the console and the widget
from `pnpm-lock.yaml`, the wheel with those pages inside, and the image itself, which installs
`uv.lock`'s versions, each checked by its hash. Every base image is named by its digest. A release
names the image by its tag and by the digest the registry holds for it, which `make deploy` asks,
so a pod pulls those bytes wherever the tag is moved to. Every push and pull request is also scanned (`check.yml`, `supply
chain`): the image's locked dependencies against the advisories (pip-audit), every commit for a
secret (gitleaks), and `infra/` with each chart rendered as production releases it for a
misconfiguration (trivy, HIGH and CRITICAL). What trivy finds and is let stand is
`infra/trivy-ignore.yaml`, each by its path and with why; the owed ones carry a date, past which
the check fails again.

A cluster has three releases and each has its target: `make edge`, `make postgres` and `make deploy`.
A deploy of the runtime releases charts/pinecall and nothing else, so a change to the front door or to
Postgres goes out when somebody means it to, after `make diff` showed it. Before it touches the
cluster `make deploy` checks three things and says what to do when one fails: `infra/charts` is what
the commit `TAG` holds, the image of `TAG` exists in the registry, and no release of the chart was
left half-way. It runs the migrations before anything new starts (a pre-upgrade hook), waits for every
workload, and knocks at the production name,
which it asks of the cluster. When the upgrade fails or is cut, Helm goes back to the release that
ran, by itself (`--rollback-on-failure`).

**Going back.** `make rollback CLUSTER=<cluster>` returns charts/pinecall to the release before this one
(`REV=<n>` names another; the target prints the last five). It brings back the image and the
chart's objects, never the database: a migration is written so the release before it still runs on
its schema (a column is added in one release and read in the next, dropped only after no release
that reads it can come back), which is what makes going back safe.
The secrets never leave Secret Manager but into the pods' environment, each pod the ones its
verb reads: the gateway the database, the signal, the vault key, the operator's key, its own
signing key, the LiveKit pair and both fleets' keys (`pinecall-fleets`, drawn by Terraform); a worker
and the overflow the LiveKit pair, their fleet's key and
the recordings store, never the database, the vault, the operator's or the signing key (rule 24 holds the templates to it);
the retention the database, the vault and the store; the migrations the database. The values
file holds no secret.

The gateway connects to Postgres as `pinecall_app`, a role that reads and writes every table's rows
and changes no table: CloudNativePG makes it from `pinecall-postgres-runtime` (charts/postgres, its
password `postgres-app-password` in Secret Manager), and the migrations, which run as the
database's owner, grant it each release (`PINECALL_DB_APP_ROLE`, waiting two minutes for the role
the first time). The owner keeps the migrations, the nightly retention (it makes and drops the
log's days). A gateway that reaches the database cannot drop,
alter or truncate a table. The first release with it needs `make tf-apply` before, for the secret.
charts/postgres reads Secret Manager through a store of its own (`pinecall-postgres`), so a cluster
from nothing comes up in the order `make edge`, `make postgres`, `make deploy`: the role's secret exists before
charts/pinecall's migrations wait for the role, and CloudNativePG watches it (`cnpg.io/reload`),
so the role is made the moment the secret lands rather than at its next pass.

Every pod of the runtime's image runs as its user (10001), with no capability, no privilege to
gain, the runtime's syscall filter and a root filesystem it cannot write: what it writes goes to
`/tmp` and its home, each an emptyDir, and to the recordings' (`pinecall.podSecurity`,
`pinecall.containerSecurity`). The third-party images' pods hold to the same, each as its own
user (`pinecall.podSecurityAs`): Redis as the image's 999 with its config file on an emptyDir and
each environment's disk made its own, LiveKit and SIP as 10001 (every port they take is above 1024, so
no capability), and kubeip as its 1001.
Two NetworkPolicies (`templates/network-policies.yaml`) name who reaches each store: the gateways' Redis
the gateways alone; Postgres the gateways, the pods labelled `pinecall.io/reaches-postgres` (the
migrations, the retention, a suite's Job), its own instances and CloudNativePG's
namespace. They are enforced only on a cluster whose dataplane enforces network policies (GKE's
Dataplane V2), which `modules/gke` does not turn on: on a cluster already made, turning it on makes
the cluster again.

## The first person

A cluster from nothing has no org and nobody to sign in. The first org and its admin, an operator
of the deployment, in one line on a gateway; the invitation link is printed once:

```console
$ kubectl --context <the box's> exec deploy/pinecall-gateway -- \
    pinecall-runtime init --email you@example.com --person "Your Name"
```

That person opens the link, sets a password, and from then on signs in at `https://<the name>` and
with `pinecall login https://<the name>` from any machine. The runtime's vendor keys, what a new
org is given and more orgs are [More orgs and keys](https://docs.pinecall.io/self-hosting/your-first-org/),
from the console's Box or the same `kubectl exec`.

## A pool an environment

Both environments share the core pool (`terraform/modules/gke`, `core`): the gateways, Postgres, Redis
and Pinecall's services. Each environment has the rest of a call to itself, so a sandbox call never
shares a machine with a production call: a **media pool** of one node (`media-<env>`,
`media_type`; production's an e2-standard-4, the sandbox's an e2-standard-2) with the environment's own
LiveKit, its livekit-sip and its core workers, and a **workers pool** from 0 (`workers-<env>`,
`workers_max`: 10 nodes for production, 3 for the sandbox) for its scaled workers — from one node
where the chart's `envs.<env>.workers.scaled.min` keeps a scaled worker warm, as the sandbox's is for a
burst of simulations that cannot wait for a node (`make fleet CLUSTER=<cluster> ENV=<env> MIN=<n>` writes
that line and releases the chart at the image that runs, in about a minute; `MOST=<n>` moves the
ceiling of pods with it; the runtime's `docs/scaling.md`, "Keeping workers warm", has what each
costs). Each pool is
tainted with its name, so nothing of another environment lands there. A sandbox burst fills the
sandbox's node and its pool to its own ceiling, and nothing else.

LiveKit gives a room to a node by load and knows no pool, so each environment is a LiveKit cluster of its
own (`pinecall-livekit-<env>`), with SIP on it, the two talking through a Redis of their own
on the environment's media node (Redis's pub/sub is one per server, whatever its database: a LiveKit
sharing one with the other environment's answered that environment's SIP and refused its numbers); the gateway reaches both (`LIVEKIT_URL`, `LIVEKIT_SANDBOX_URL`) and each tells its webhook
the environment (`?world=`). A browser reaches production's at `wss://<name>` and the sandbox's at
`wss://<name>/sandbox`: `charts/edge` routes LiveKit's paths under `/sandbox` to the sandbox's
LiveKit with the prefix taken off.

## SIP's address

Google's HTTPS load balancer, the name, carries no UDP: a carrier sends an environment's calls to the
environment's SIP name (`envs.<env>.sipDomain` in the values, `PINECALL_SIP_DOMAIN`, `PINECALL_SANDBOX_SIP_DOMAIN`),
which Route 53 points at the environment's media address (`terraform/modules/edge`, `media_addresses`).
kubeip (the chart, as the identity `terraform/modules/kubeip` made) gives each environment's media node
its address, found by its label (`pinecall-media=<cluster>-<env>`), and gives it again to a node
that replaces it; the environment's LiveKit and SIP announce it (`node_ip`, `nat_1_to_1_ip`). A Twilio
trunk made before the SIP name moved is sent on once, by `pinecall-runtime sip repoint`.

The core node lost, drilled on staging (when it also held LiveKit and SIP): its VM
deleted at 01:27:50 UTC (gone at 01:29:46), the node pool made another at 01:29:48, kubeip gave it
the same address at 01:32:35, the gateways answered at 01:34:46 with Postgres ready, and four
calls then started, every turn answered. A core of one node is down for those minutes; a second
core node is the shape that is not (`docs/scaling.md`).

## HTTPS

The name is served by `charts/edge`'s Gateway (the Gateway API, `gke-l7-global-external-managed`)
on the global address `terraform/modules/edge` reserves, with a Certificate Manager certificate
proved by DNS (a CNAME each in Route 53): it is issued before a name points at the address, so a
cutover moves the names onto a certificate that is valid already. Made on staging:
the certificate active before any load balancer served it, the names answering over HTTPS on it,
plain HTTP redirected, a LiveKit room joined over its WebSocket and calls placed, the address the
Ingress had served kept.

## The secrets the operator puts

Terraform draws most of a cluster's secrets. The ones a cluster names in `given`
(`terraform/modules/secrets`) are made empty, and the operator puts each once, piped, so that no
state and no terminal holds it: `vault-key` is the key the database is sealed under (a database
moved in from elsewhere, as production's was on 2026-10-04, keeps the key it was sealed under), `s3-access-key-id` with `s3-secret-access-key` are the object
store's key, made by hand, and `turnstile-secret` is Cloudflare Turnstile's, where the values name
its site key (`turnstile.siteKey`). The cluster's `given_secrets` lists them.

```console
$ <the value> | gcloud secrets versions add pinecall-<cluster>-<name> --data-file=-
```

A recording moves to the object store `store` names in the cluster's values (endpoint, region,
bucket); unset, it stays on the pod's disk and goes with the pod. Proven on staging with the
lab's store (moto on the generator): two calls, each recording in the bucket,
sealed, under its org and call.

## Hosting

The orgs' hosted apps (`pinecall deploy`, `docs/protocol/hosting.md`) run on a cluster of their
own, `terraform/modules/hosting`, made where the cluster's variables say `hosting = true`: a GKE
Autopilot cluster in a VPC of its own, so an org's code never shares a network with the platform's
database, its gateways or its calls. Off, the runtime serves everything but hosted apps.

| what | where |
|---|---|
| each app | one pod in `pinecall-apps`, under GKE Sandbox's gVisor (`runtimeClassName: gvisor`): installed by its first container from its runner's sources, run by its second, read-only, as a user that is not root, with no service account token |
| the fence | `charts/hosting`'s network policy: an app's pod reaches the internet and its runner's sources, nothing private (no pod, node or network address), and nothing reaches it |
| each environment's runner | a pod of `pinecall-runner` (`pinecall-runtime runner start`), knocking the platform at its public name with its environment's runner key, read off Secret Manager by the one identity that may (`pinecall-<cluster>-runner`); in `pinecall-apps` it may create, read, replace and delete the apps' pods and secrets and read their logs, nothing else |

The two runner keys are minted by the platform and put once, piped, never printed:

```console
$ kubectl --context <the box's> exec deploy/pinecall-gateway -- pinecall-runtime keys runner production \
    | gcloud secrets versions add pinecall-<cluster>-runner-key-production --data-file=-
$ make hosting CLUSTER=<cluster> TAG=<commit>       # the runners, the namespace and its fence
```

An app's pod runs `appImage`. Node's own image installs a TypeScript project; a Python project is
installed with uv onto the CPython 3.13 of `images/app` (with the system's certificate roots, which
CPython reads and Node's slim image lacks), built once into the registry under a new tag each change and named in
`$OPS/values/hosting-<cluster>.yaml` — on Node's image a Python release fails its install and says so:

```console
$ gcloud builds submit infra/images/app --config infra/images/cloudbuild.yaml \
    --service-account "$(terraform -chdir=infra/terraform/project output -raw build_service_account)" \
    --substitutions _IMAGE="$(terraform -chdir=infra/terraform/project output -raw registry)/app:node24-py3.13-2"
```

## From a deployment (history)

Before 2026-10-04 the runtime also ran on a single machine, a "box", and production moved from one
into this cluster that day. That install is gone: nothing here makes a deployment or runs on one. What is
left is the one-time migration that moved its database, kept for an operator who still holds one:
`make restore-from-box CLUSTER=<cluster> BOX=<ssh alias>` (refused for `CLUSTER=production`) empties the cluster's schema, makes its two
extensions again, and restores the platform's schema `public` and its rows into it as the database's
owner, the dump streamed from the platform into the Postgres pod and deleted there. The platform's runtime is
stopped first, and the runtime's chart is installed after. Rehearsed on
staging with a deployment's database of some 43 000 log rows: restored in 43 s, every row and migration
there, the chart installed on it, the live suite green, the platform's orgs, fleet and carriers served.

## Backups, and a restore

Postgres's WAL goes to the bucket of `terraform/modules/backups` as it is written, and a base
backup is taken each night at 03:00 UTC (`charts/postgres`: the Barman Cloud plugin, 35 days
kept), as an identity that touches that bucket alone. WAL alone restores nothing, so a database
just installed or just restored is backed up once by hand, a `Backup` of `method: plugin`. A
restore is a second Cluster recovered from the bucket, which the same identity reads as
`pinecall-postgres-restore`:

```yaml
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: pinecall-postgres-restore
spec:
  instances: 1
  imageName: <charts/postgres's image>
  postgresql:
    shared_preload_libraries: [pg_textsearch]
  storage: { size: 20Gi, storageClass: standard-rwo }
  serviceAccountTemplate:
    metadata:
      annotations:
        iam.gke.io/gcp-service-account: <terraform output postgres_backups_service_account>
  bootstrap:
    recovery: { source: origin }      # recoveryTarget: { targetTime: "…" } for a minute of the window
  externalClusters:
    - name: origin
      plugin:
        name: barman-cloud.cloudnative-pg.io
        parameters: { barmanObjectName: pinecall-postgres, serverName: pinecall-postgres }
```

Drilled on staging on 2026-10-04: a base backup in 9 s, the restore ready in 106 s with the same
30 514 rows of `call_log`, the same last entry and the same 48 migrations as the live database.

## Alerts

The alerts are written once, as a Prometheus rule file: `charts/pinecall/alerts.yaml`. Who
collects the metrics and evaluates the rules is the cluster's `monitoring.collector` in its values
(`OPS/values/<cluster>.terraform.json` on Google Cloud, where Terraform says it), which both charts
read and neither guesses (unset, the release fails):

| `monitoring.collector` | collects | evaluates and tells |
|---|---|---|
| `gmp` (Google Cloud) | Google's Managed Prometheus: a `PodMonitoring` for the gateways and one for Postgres | `terraform/modules/alerts`, a Cloud Monitoring policy for each rule (scoped to the cluster, as a project holds several), mailed to the cluster's `alert_emails`, and an uptime check of the name |
| `prometheus-operator` (any other cluster: EKS, AKS, your own) | the cluster's Prometheus: a `PodMonitor` for each | the cluster's Prometheus, `alerts.yaml` carried as the chart's `PrometheusRule`; Alertmanager tells whom it is told to, and the name's check from outside is that cloud's own (a Route 53 health check, a blackbox exporter) |
| `none` | nothing | nothing |

`monitoring.namespace` is where the collector runs, admitted by the Postgres policy to the
metrics' port (9187); the gateways' `/metrics` answer the pod network (`PINECALL_METRICS_FROM`).

The rules: a write to the log slow (p99 over 250 ms for 5 minutes), a fleet over 80% of its seats
for 5 minutes, a vendor over its error line for 2 minutes; no gateway answering its collector, a
gateway's reaper or sweep stopped (`pinecall_loop_running`), Postgres not answering
(`cnpg_collector_up`), each for 2 minutes; the WAL failing to reach the bucket for 15 minutes (the
backups stop there). On Google Cloud, the name failing from outside too (`/.well-known/pinecall`
every minute from Google's regions, more than one failing for 2 minutes: the load balancer, its
certificate, every gateway). Each address in `alert_emails` is verified once, by the code Google
mails it.

## Services of your own

A service of the operator's own (a notifier, billing) runs on the same cluster as its own chart,
released beside the runtime's and never part of it: its name (`services` in the cluster's variables) an
`HTTPRoute` on this Gateway under `modules/edge`'s services certificate, its credentials the
secret store's (`given_secrets`), the runtime reached at `http://pinecall-gateway:8080` with the
ops key. A notifier that signs pushes does it as `modules/notify`'s identity
(`firebase_project`).

## Staging, made and destroyed

Staging is made for a proof and destroyed after it: the runtime's own releases first, so no object is left waiting on a controller Terraform removes,
then Terraform:

```console
$ for r in pinecall pinecall-edge pinecall-postgres; do helm --kube-context <staging> uninstall $r --wait; done
$ gcloud storage rm -r "gs://pinecall-staging-postgres-<project number>/**"
$ cd infra/terraform/cluster && export TF_DATA_DIR=$PWD/.terraform/staging
$ terraform plan -destroy -var name=staging -var-file=$OPS/terraform/staging.tfvars -var-file=$OPS/terraform/staging.fence.tfvars.json -var lab=true -out=staging.plan && terraform apply staging.plan
```

## Proven

On staging: every suite, 3 113 tests, green inside the cluster against Postgres
17.11 under CloudNativePG 1.30.1, pgvector 0.8.6 and pg_textsearch 1.4.0 preloaded, the runtime
connecting as the database's owner, no superuser. The chart released: two gateways, LiveKit and
SIP on the core node's network, each environment's two core workers registered with LiveKit under their
own names, the overflow, and KEDA reading the gateway's number (0, no scaled worker). With
calls, the same day, by the lab: 24 of 24 and 32 of 32 started, every turn answered, KEDA growing
to two scaled workers and the autoscaler to two nodes; a worker node reset under 16 calls, 16 of
16 started; a release during 16 calls, none cut; Postgres's pod deleted under 8, every call written
whole. The table and what it says of the core node: `docs/scaling.md`, "The burst".
