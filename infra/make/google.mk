# Google Cloud's side of the runtime's Makefile (PROVIDER = google, the default): who Terraform acts
# as, where the cluster and its registry are, how an image is built and found, where the hosted apps
# run. The operator's <cluster>.mk gives PROJECT, and REGION, ZONE or CONTEXT where they are not
# these. What a provider's file must define is the list in infra/README.md, "Another cloud".

REGION   ?= us-central1
ZONE     ?= $(REGION)-c
CONTEXT  ?= gke_$(PROJECT)_$(ZONE)_pinecall-$(NAME)

# Google's credentials are the gcloud login's, handed to Terraform as a short-lived token in the
# environment, never printed.
TF_AUTH   = GOOGLE_OAUTH_ACCESS_TOKEN="$$(gcloud auth print-access-token)"

# The images: Artifact Registry (terraform/google/project), built by Cloud Build as the builds' own
# identity, never on the laptop.
REGISTRY ?= $(REGION)-docker.pkg.dev/$(PROJECT)/pinecall
BUILDER  ?= projects/$(PROJECT)/serviceAccounts/pinecall-build@$(PROJECT).iam.gserviceaccount.com
# How each kind of image is built: the runtime's and the MCP server's from a commit's whole tree,
# each checked before it is pushed; any other from the Containerfile at its context's root.
build_runtime = $(INFRA)/images/runtime/cloudbuild.yaml
build_mcp     = $(INFRA)/images/mcp/cloudbuild.yaml
build_plain   = $(INFRA)/images/cloudbuild.yaml
# $(call build,<the context: a folder or a .tar.gz>,<runtime|mcp|plain>,<image>:<tag>)
build     = gcloud builds submit $(1) --config $(build_$(2)) --service-account $(BUILDER) \
	  --substitutions _IMAGE=$(3) --project $(PROJECT) --region $(REGION)
# $(call digest,<image>:<tag>): what the registry holds for it (`sha256:…`), or nothing.
digest    = $$(gcloud artifacts docker images describe $(1) --project $(PROJECT) --format='value(image_summary.digest)' 2>/dev/null)

# The hosting cluster (terraform/google/modules/hosting): a regional Autopilot cluster of its own.
HOSTING  ?= gke_$(PROJECT)_$(REGION)_pinecall-$(NAME)-hosting
hosting_credentials = gcloud container clusters get-credentials pinecall-$(NAME)-hosting --region $(REGION) \
	  --project $(PROJECT) >/dev/null
