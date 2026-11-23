# A runtime on one machine (`pinecall-runtime setup --domain`, runtime/docs/the-runtime-cli.md): the
# gateway, each environment's worker and overflow, Postgres, Redis, LiveKit, SIP and Caddy in Docker,
# and beside it a second, smaller machine that runs the hosted apps and nothing else, so the code of
# an org never runs where the database and the vault's key are. The cluster root (../cluster) is the
# other shape of the same deployment, for more calls than a machine holds.

variable "name" {
  type        = string
  description = "staging or production: everything made is named pinecall-<name>-server."

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,20}$", var.name))
    error_message = "Lowercase letters, digits and dashes, at most 21: it is part of every name made."
  }
}

variable "project" {
  type        = string
  description = "The Google Cloud project the machines are made in."
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "zone" {
  type        = string
  description = "The zone both machines run in."
  default     = "us-central1-c"
}

variable "range" {
  type        = string
  description = "The range of the network made for the two machines, a /24 or wider."
  default     = "10.150.0.0/24"
}

# What a machine is: the server sized for its calls (a spoken call was measured at about a third of
# a core with the platform's part, and a worker stops taking calls past 70 % of its cores), the
# apps' machine for its apps (each about 200 MiB at rest, and a gibibyte while it installs).
variable "machines" {
  type = object({
    server      = optional(string, "e2-standard-4")
    server_disk = optional(number, 80)
    apps        = optional(string, "e2-standard-2")
    apps_disk   = optional(number, 40)
  })
  description = "Each machine's type and its disk in GiB."
  default     = {}
}

variable "apps" {
  type        = bool
  description = "Whether the hosted apps' machine is made: a deployment with no hosted app has none."
  default     = true
}

variable "dns_zone" {
  type        = string
  description = "The Route 53 zone the names are records of."
}

variable "names" {
  type        = list(string)
  description = "The server's names: the platform's first, then any other the same proxy answers."
}

variable "services" {
  type        = list(string)
  description = "Names of services of your own at the same proxy, each a file of the server's sites/."
  default     = []
}

variable "pages" {
  type        = string
  description = "The domain the apps' pages are served under (`*.<pages>` points at the server), or empty."
  default     = ""
}

variable "sip_names" {
  type        = list(string)
  description = "The names carriers send calls to: every one points at the server, whose one SIP takes both environments' calls."
  default     = []
}

# The order of a move: the machines made and the runtime set up on them with the names still
# elsewhere (`setup --unpointed`), tried by its address, and only then the names moved here. A record
# that exists is taken over in one change; whoever held it then forgets it (`terraform state rm`).
variable "point_names" {
  type        = bool
  description = "Whether the names, the services' and the pages' point at the server."
  default     = false
}

variable "point_sip" {
  type        = bool
  description = "Whether the SIP names point at the server."
  default     = false
}

# An address carriers and PBXs already know, kept from a deployment before this one: the name it is
# reserved under. Left null, an address is reserved, and it outlives every machine that holds it.
variable "kept_address" {
  type        = string
  description = "The name of a reserved address of the region the server takes instead of a new one."
  default     = null
}

variable "rtp_ports" {
  type        = string
  description = "The range SIP's audio uses, a port a call: the server's PINECALL_SIP_RTP_PORTS."
  default     = "10000-10199"

  validation {
    condition     = can(regex("^[0-9]+-[0-9]+$", var.rtp_ports))
    error_message = "A range of ports, as 10000-10199."
  }
}

# The networks the orgs' carriers call from, as the gateway approved them: written by `make tf-fence`
# into the operator's <name>.fence.tfvars.json. No default, on purpose: with one, a checkout that
# lacked the file would plan 5060 closed to every carrier. A server with no carrier says `[]`.
variable "sip_sources" {
  type        = list(string)
  description = "The networks 5060 opens to, each a CIDR; an empty list opens it to nobody."

  validation {
    condition     = alltrue([for source in var.sip_sources : can(cidrnetmask(source)) || can(cidrhost(source, 0))])
    error_message = "Each of sip_sources is a network in CIDR form (203.0.113.0/24, 2001:db8::/32)."
  }
}

# The deployment's own secrets in Secret Manager: what its database is sealed and signed with (the
# vault's key, the tokens' key, the operator's key, the fleets' and the runners' keys) and what its
# services pay and sign with, kept outside the machine so a server made again begins its env file
# from them. Terraform makes each name; the operator puts each value, piped, and no state holds one
# (`gcloud secrets versions add <id> --data-file=-`). The server alone reads them: the apps' machine
# runs other people's code and reads none it is not named.
variable "keeps_secrets" {
  type        = list(string)
  description = "The ids of the Secret Manager secrets this deployment keeps, as pinecall-production-vault-key."
  default     = []
}

# Before a runtime moves here from a cluster, its secrets are still that cluster's: the server may
# read the Secret Manager secrets named here. After the move the ids go to `keeps_secrets`
# (infra/README.md, "From a cluster to a server").
variable "reads_secrets" {
  type        = list(string)
  description = "The ids of another deployment's Secret Manager secrets the server may read."
  default     = []
}

# The secrets the apps' machine may read, each one of `keeps_secrets`: none unless named. Whatever is
# named here is within reach of every hosted app's code, so it is never a key that opens more than
# those apps already hold.
variable "apps_reads_secrets" {
  type        = list(string)
  description = "The ids, among keeps_secrets, the apps' machine may read. Empty: it reads none."
  default     = []
}
