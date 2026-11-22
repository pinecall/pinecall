# What one cluster is told: `make` gives its name, the operator's <cluster>.tfvars the rest. The
# names, the SIP names, the carriers' networks, the secrets and the services are said as
# terraform/google/cluster says them; what differs is what a cloud is made of.

variable "name" {
  type        = string
  description = "The cluster's name, carried by everything made for it (pinecall-<name>). `make` gives it as NAME (CLUSTER unless the operator's <cluster>.mk says another)."

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,20}$", var.name))
    error_message = "A cluster's name is lowercase letters, digits and dashes (production, staging)."
  }
}

variable "region" {
  type        = string
  description = "The region of the cluster, its addresses, its secrets and its backups."
  default     = "us-east-1"
}

variable "zones" {
  type        = list(string)
  description = "Two availability zones of the region: every node runs in the first; the control plane and the load balancer ask for a second."
  default     = ["us-east-1a", "us-east-1b"]
}

variable "kubernetes" {
  type        = string
  description = "The cluster's Kubernetes version, one in EKS's standard support (`aws eks describe-cluster-versions`)."
  default     = "1.36"
}

variable "deletion_protection" {
  type        = bool
  description = "Whether AWS refuses to delete the cluster. Off only for a cluster made for a proof and destroyed after it."
  default     = true
}

# The cluster's private ranges: its VPC's, which its nodes and their pods take their addresses from
# (a pod's is one of its node's subnet), and its Services', outside it. The charts are told the
# nodes' subnet (media.nodeNetwork, gateway.podNetwork).
variable "ranges" {
  type        = object({ vpc = string, services = string })
  description = "The cluster's private ranges, each a CIDR: the VPC's a /16."
}

# The machines, each pool's: said here once, and a value of the operator's own where it differs.
# A scaled worker asks for six cores and 12 GiB (charts/pinecall), one a node. The core node, which
# holds the database and the gateways, and production's media node are no burstable type: neither a
# statement nor audio can wait for a credit, and on a t3a core the suites' slower tests ran past
# their ten seconds (2026-11-22).
variable "pools" {
  type = object({
    core        = optional(string, "m6a.xlarge")
    media       = optional(map(string), { production = "m6a.xlarge", sandbox = "t3a.large" })
    workers     = optional(string, "c6a.2xlarge")
    workers_max = optional(map(number), { production = 10, sandbox = 3 })
    hosting     = optional(string, "t3a.large")
    hosting_max = optional(number, 4)
  })
  description = "Each pool's instance type, and the ceilings of the pools that grow."
  default     = {}
}

variable "admins" {
  type        = list(string)
  description = "IAM users or roles, besides whoever makes the cluster, that are its admins: each an ARN."
  default     = []
}

variable "api_sources" {
  type        = list(string)
  description = "The networks the cluster's API answers from the internet, each a CIDR."
  default     = ["0.0.0.0/0"]
}

variable "dns_zone" {
  type        = string
  description = "The Route 53 zone every name below is a record of."
}

variable "names" {
  type        = list(string)
  description = "The names the cluster is served at, every one of them both envs; the first is PINECALL_DOMAIN."
}

# The names point at this cluster's load balancer, which charts/edge makes: off before its first
# release (there is none to point at) and while another deployment still answers them.
variable "point_names" {
  type        = bool
  description = "Whether the names' records point at this cluster."
  default     = false
}

variable "sip_names" {
  type        = map(string)
  description = "Each env's SIP name, at the env's media address: a carrier's alone (PINECALL_SIP_DOMAIN, PINECALL_SANDBOX_SIP_DOMAIN)."
}

# Off while the carriers still send each env's calls to another deployment's address.
variable "point_sip" {
  type        = bool
  description = "Whether the SIP names' records point at this cluster's media addresses."
  default     = false
}

variable "services" {
  type        = list(string)
  description = "Names of services of your own served at the same Gateway, each by its own chart; none by default."
  default     = []
}

variable "point_services" {
  type        = bool
  description = "Whether the services' records point at this cluster."
  default     = false
}

variable "pages" {
  type        = string
  description = "The domain the apps' own pages are served under (`<app>--<org>.<pages>`); empty serves none."
  default     = ""
}

# The networks the orgs' carriers call from, as the gateway approved them: written by `make tf-fence`
# into ops/terraform/<cluster>.fence.tfvars.json, a file that is versioned there and read before a
# plan. No default, on purpose: with one, a checkout that lacked the file planned the firewall's
# removal and 5060 closed to every carrier (2026-10-21). A cluster with no carrier says `[]`.
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

variable "secrets_recovery_days" {
  type        = number
  description = "How long a deleted secret is kept and its name held: 0 for a cluster made for a proof and made again."
  default     = 7
}

# Where the orgs' hosted apps run (modules/hosting): a fenced pool of this cluster. Off, the runtime
# serves everything but `pinecall deploy`.
variable "hosting" {
  type        = bool
  description = "Whether the pool of the orgs' hosted apps is made."
  default     = false
}
