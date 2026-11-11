# What one cluster is told: `make` gives its name, the operator's <name>.tfvars the rest.

variable "name" {
  type        = string
  description = "The cluster's name, carried by everything made for it (pinecall-<name>). `make` gives it as ENV, which also picks the variables and the state, so the three cannot disagree."

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,20}$", var.name))
    error_message = "A cluster's name is lowercase letters, digits and dashes (production, staging)."
  }
}

variable "project" {
  type        = string
  description = "The Google Cloud project the cluster is made in."
}

variable "region" {
  type        = string
  description = "The region of the cluster's addresses, its subnet and its backups."
  default     = "us-central1"
}

variable "zone" {
  type        = string
  description = "The zone the cluster and its nodes run in."
  default     = "us-central1-c"
}

variable "deletion_protection" {
  type        = bool
  description = "Whether Google refuses to delete the cluster. Off only for a cluster made for a proof and destroyed after it."
  default     = true
}

# The cluster's private ranges (modules/gke): its nodes' subnet, its pods' and its services'. The
# charts are told the first two (media.nodeNetwork, gateway.podNetwork).
variable "ranges" {
  type        = object({ nodes = string, pods = string, services = string })
  description = "The cluster's private ranges, each a CIDR."
}

variable "dns_zone" {
  type        = string
  description = "The Route 53 zone every name below is a record of."
}

variable "names" {
  type        = list(string)
  description = "The names the cluster is served at, every one of them both worlds; the first is PINECALL_DOMAIN."
}

# The names point at this cluster's address; off while another box still answers them.
variable "point_names" {
  type        = bool
  description = "Whether the names' records point at this cluster."
  default     = true
}

variable "sip_names" {
  type        = map(string)
  description = "Each world's SIP name, at the world's media address: a carrier's alone (PINECALL_SIP_DOMAIN, PINECALL_SANDBOX_SIP_DOMAIN)."
}

variable "kept_addresses" {
  type        = map(string)
  description = "A world's media address kept from before, by its reserved name (carriers know it)."
  default     = {}
}

variable "services" {
  type        = list(string)
  description = "Names of services of your own served at the same Gateway, each by its own chart; none by default."
  default     = []
}

# The services' names point at this cluster's address; off while they are served elsewhere.
variable "point_services" {
  type        = bool
  description = "Whether the services' records point at this cluster."
  default     = true
}

variable "pages" {
  type        = string
  description = "The domain the apps' own pages are served under (`<app>--<org>.<pages>`); empty serves none."
  default     = ""
}

# The networks the orgs' carriers call from, as the gateway approved them: written by `make tf-fence`
# into ops/terraform/<name>.fence.tfvars.json, a file that is versioned there and read before a plan.
# No default, on purpose: with one, a checkout that lacked the file planned the firewall's removal and
# 5060 closed to every carrier (2026-10-21). A plan with no file fails; a cluster with no carrier says `[]`.
variable "sip_sources" {
  type        = list(string)
  description = "The networks 5060 opens to, each a CIDR; an empty list opens it to nobody."

  validation {
    condition     = alltrue([for source in var.sip_sources : can(cidrnetmask(source)) || can(cidrhost(source, 0))])
    error_message = "Each of sip_sources is a network in CIDR form (203.0.113.0/24, 2001:db8::/32)."
  }
}

# Secrets the operator puts by hand, each made empty here: the vault key and the ops key the
# runtime needs, the object store's key when recordings leave the pod, and any of the operator's
# own services' that read the same store.
variable "given_secrets" {
  type        = list(string)
  description = "The secrets made empty for the operator to put a value in."
  default     = ["vault-key", "ops-key"]
}

variable "alert_emails" {
  type        = list(string)
  description = "Who the cluster's alerts are mailed to; nobody, and no alert is made."
  default     = []
}

# A notifier of the operator's own signs Android's pushes in this Firebase project (modules/notify);
# unset, no identity for it is made.
variable "firebase_project" {
  type        = string
  description = "The Firebase project a notifier of the operator's signs pushes in."
  default     = null
}

# The hosting cluster (modules/hosting): where the orgs' hosted apps run. Off, the runtime serves
# everything but `pinecall deploy`.
variable "hosting" {
  type        = bool
  description = "Whether the cluster of the orgs' hosted apps is made."
  default     = false
}

# The hosting cluster's, apart from the cluster's (modules/hosting); its runners take fixed
# addresses of `services` (charts/hosting, worlds).
variable "hosting_ranges" {
  type        = object({ nodes = string, pods = string, services = string })
  description = "The hosting cluster's private ranges, each a CIDR; asked for when `hosting` is on."
  default     = null
}

# The voice lab beside the cluster, for a proof with calls (infra/lab): `-var lab=true`.
variable "lab" {
  type        = bool
  description = "Whether the lab's call generator stands beside the cluster."
  default     = false
}
